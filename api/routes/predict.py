import asyncio
import time
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from api.schemas import (
    BatchPredictionResponse,
    BatchTransactionRequest,
    PredictionResponse,
    TransactionRequest,
)
from shared.logger import get_logger

logger = get_logger("api_predict")
router = APIRouter(tags=["Risk Prediction"])


def _update_feature_store_task(feature_store: Any, tx_data: dict[str, Any]) -> None:
    """
    Background Task: Asynchronously updates customer velocity counters in Redis
    without impacting the synchronous <100ms prediction SLA.
    """
    try:
        if not feature_store or not getattr(feature_store, "client", None):
            return

        card1 = str(tx_data.get("card1", "missing"))
        card2 = str(tx_data.get("card2", "missing"))
        if card1 != "missing":
            uid = f"{card1}_{card2}"
            # Increment transaction counter and update last seen timestamp in Redis
            pipeline = feature_store.client.pipeline()
            pipeline.hincrby(f"customer:{uid}", "tx_count_total", 1)
            if "TransactionDT" in tx_data:
                pipeline.hset(f"customer:{uid}", "last_seen_dt", tx_data["TransactionDT"])
            pipeline.execute()
    except Exception as e:
        logger.warning(f"Background feature store update failed: {e}")


@router.post(
    "/predict",
    response_model=PredictionResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate Single Transaction Risk",
    description="Scores a single incoming transaction within <100ms SLA by combining raw input with Redis profile.",
)
async def predict_transaction(transaction: TransactionRequest, background_tasks: BackgroundTasks, request: Request) -> PredictionResponse:
    inference_pipeline = getattr(request.app.state, "inference_pipeline", None)
    if inference_pipeline is None or getattr(inference_pipeline, "model", None) is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Risk Intelligence Engine is warming up or model is unavailable.")

    tx_dict = transaction.model_dump(exclude_none=False)

    try:
        # Offload CPU-bound ML inference to a threadpool to prevent freezing the event loop
        result = await asyncio.to_thread(inference_pipeline.predict, tx_dict)
    except Exception as exc:
        logger.error(f"Prediction computation failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference execution failed: {exc}",
        ) from exc

    # Trigger asynchronous background telemetry / cache update
    if hasattr(inference_pipeline, "feature_store"):
        background_tasks.add_task(_update_feature_store_task, inference_pipeline.feature_store, tx_dict)

    request_id = getattr(request.state, "request_id", None)
    tx_id = str(tx_dict.get("TransactionID")) if tx_dict.get("TransactionID") is not None else None

    return PredictionResponse(
        transaction_id=tx_id,
        risk_score=result["risk_score"],
        risk_level=result["risk_level"],
        fraud_probability=result["fraud_probability"],
        latency_ms=result["latency_ms"],
        request_id=request_id,
    )


@router.post(
    "/predict/batch",
    response_model=BatchPredictionResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate Batch of Transactions",
    description="Vectorized high-throughput scoring for multiple transactions in a single forward pass.",
)
async def predict_batch_transactions(batch_req: BatchTransactionRequest, request: Request) -> BatchPredictionResponse:
    inference_pipeline = getattr(request.app.state, "inference_pipeline", None)
    if inference_pipeline is None or getattr(inference_pipeline, "model", None) is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Risk Intelligence Engine is warming up or model is unavailable.")

    tx_list = [tx.model_dump(exclude_none=False) for tx in batch_req.transactions]
    num_tx = len(tx_list)
    request_id = getattr(request.state, "request_id", None)

    batch_start = time.perf_counter()
    try:
        # Vectorized batch prediction offloaded to worker thread
        results = await asyncio.to_thread(inference_pipeline.predict_batch, tx_list)
    except Exception as exc:
        logger.error(f"Batch prediction failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch inference failed: {exc}",
        ) from exc

    total_batch_latency_ms = (time.perf_counter() - batch_start) * 1000
    throughput = (num_tx / (total_batch_latency_ms / 1000.0)) if total_batch_latency_ms > 0 else 0.0

    prediction_responses = [
        PredictionResponse(
            transaction_id=item.get("transaction_id"),
            risk_score=item["risk_score"],
            risk_level=item["risk_level"],
            fraud_probability=item["fraud_probability"],
            latency_ms=item["latency_ms"],
            request_id=request_id,
        )
        for item in results
    ]

    return BatchPredictionResponse(
        predictions=prediction_responses,
        total_transactions=num_tx,
        batch_latency_ms=round(total_batch_latency_ms, 2),
        throughput_tx_per_sec=round(throughput, 2),
    )
