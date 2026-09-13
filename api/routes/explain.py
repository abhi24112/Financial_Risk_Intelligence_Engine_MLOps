import asyncio
import time
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException, Request, status

from api.schemas import (
    BatchExplainRequest,
    BatchExplainResponse,
    ExplainRequest,
    ExplainResponse,
)
from explainability.shap_engine import SHAPEngine
from shared.logger import get_logger

logger = get_logger("api_explain")
router = APIRouter(tags=["Explainability Engine"])


def _extract_estimator(model: Any) -> Any:
    """Helper to extract underlying tree estimator from scikit-learn pipeline if wrapped."""
    if hasattr(model, "named_steps") and "model" in model.named_steps:
        return model.named_steps["model"]
    return model


def _compute_single_explanation(
    inference_pipeline: Any,
    shap_engine: SHAPEngine,
    raw_tx: dict[str, Any],
    top_k: int,
) -> dict[str, Any]:
    """
    Synchronous helper executed in worker thread for single SHAP explanation computation.
    """
    start_time = time.perf_counter()

    # 1. Get prediction
    pred_res = inference_pipeline.predict(raw_tx)

    # 2. Build preprocessed numeric dataframe
    df_features = inference_pipeline._build_features(raw_tx)

    # 3. Extract estimator
    estimator = _extract_estimator(inference_pipeline.model)
    tx_id = raw_tx.get("TransactionID", "tx_current")

    # 4. Generate SHAP explanation
    explanations = shap_engine.explain(
        model=estimator,
        X_sample=df_features,
        X_shap=df_features,
        tx_ids=[tx_id],
        top_k=top_k,
    )

    tx_explain = explanations.get(str(tx_id), {"top_features": [], "shap_values": [], "reasons": []})
    latency_ms = (time.perf_counter() - start_time) * 1000

    return {
        "transaction_id": str(tx_id) if raw_tx.get("TransactionID") is not None else None,
        "risk_score": pred_res["risk_score"],
        "risk_level": pred_res["risk_level"],
        "fraud_probability": pred_res["fraud_probability"],
        "top_features": tx_explain["top_features"],
        "shap_values": tx_explain["shap_values"],
        "reasons": tx_explain["reasons"],
        "latency_ms": round(latency_ms, 2),
    }


def _compute_batch_explanations(
    inference_pipeline: Any,
    shap_engine: SHAPEngine,
    raw_tx_list: list[dict[str, Any]],
    top_k: int,
) -> dict[str, Any]:
    """
    Synchronous helper executed in worker thread for high-throughput batch SHAP explanations.
    """
    batch_start = time.perf_counter()

    # 1. Vectorized Batch Predictions
    batch_preds = inference_pipeline.predict_batch(raw_tx_list)

    # 2. Vectorized Feature Extraction
    dfs = [inference_pipeline._build_features(tx) for tx in raw_tx_list]
    combined_df = pd.concat(dfs, ignore_index=True)

    # 3. Generate transaction IDs for tracking
    tx_ids = [str(tx.get("TransactionID", f"tx_{idx}")) for idx, tx in enumerate(raw_tx_list)]

    # 4. Extract estimator and execute batch SHAP TreeExplainer
    estimator = _extract_estimator(inference_pipeline.model)
    explanations = shap_engine.explain(
        model=estimator,
        X_sample=combined_df,
        X_shap=combined_df,
        tx_ids=tx_ids,
        top_k=top_k,
    )

    total_batch_latency_ms = (time.perf_counter() - batch_start) * 1000
    avg_latency_ms = total_batch_latency_ms / len(raw_tx_list)

    response_items = []
    for idx, raw_tx in enumerate(raw_tx_list):
        t_id = tx_ids[idx]
        pred_item = batch_preds[idx]
        tx_explain = explanations.get(t_id, {"top_features": [], "shap_values": [], "reasons": []})

        response_items.append(
            ExplainResponse(
                transaction_id=str(raw_tx.get("TransactionID")) if raw_tx.get("TransactionID") is not None else None,
                risk_score=pred_item["risk_score"],
                risk_level=pred_item["risk_level"],
                fraud_probability=pred_item["fraud_probability"],
                top_features=tx_explain["top_features"],
                shap_values=tx_explain["shap_values"],
                reasons=tx_explain["reasons"],
                latency_ms=round(avg_latency_ms, 2),
            )
        )

    return {
        "explanations": response_items,
        "total_transactions": len(raw_tx_list),
        "batch_latency_ms": round(total_batch_latency_ms, 2),
    }


@router.post(
    "/explain",
    response_model=ExplainResponse,
    status_code=status.HTTP_200_OK,
    summary="Explain Transaction Risk",
    description="Decoupled SHAP endpoint that provides analyst-readable reasons for why a transaction was flagged.",
)
async def explain_transaction(req: ExplainRequest, request: Request) -> ExplainResponse:
    inference_pipeline = getattr(request.app.state, "inference_pipeline", None)
    shap_engine = getattr(request.app.state, "shap_engine", None)

    if inference_pipeline is None or getattr(inference_pipeline, "model", None) is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Model is currently unavailable.")

    if shap_engine is None:
        shap_engine = SHAPEngine()

    raw_tx = req.transaction.model_dump(exclude_none=False)

    try:
        result = await asyncio.to_thread(_compute_single_explanation, inference_pipeline, shap_engine, raw_tx, req.top_k)
    except Exception as exc:
        logger.error(f"SHAP explanation failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Explanation calculation failed: {exc}",
        ) from exc

    return ExplainResponse(
        transaction_id=result.get("transaction_id"),
        risk_score=result["risk_score"],
        risk_level=result["risk_level"],
        fraud_probability=result["fraud_probability"],
        top_features=result["top_features"],
        shap_values=result["shap_values"],
        reasons=result["reasons"],
        latency_ms=result["latency_ms"],
    )


@router.post(
    "/explain/batch",
    response_model=BatchExplainResponse,
    status_code=status.HTTP_200_OK,
    summary="Batch Explain Transaction Risk",
    description="Vectorized SHAP endpoint that provides batch risk explanations for up to 50 transactions.",
)
async def explain_transaction_batch(req: BatchExplainRequest, request: Request) -> BatchExplainResponse:
    inference_pipeline = getattr(request.app.state, "inference_pipeline", None)
    shap_engine = getattr(request.app.state, "shap_engine", None)

    if inference_pipeline is None or getattr(inference_pipeline, "model", None) is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Model is currently unavailable.")

    if shap_engine is None:
        shap_engine = SHAPEngine()

    raw_tx_list = [tx.model_dump(exclude_none=False) for tx in req.transactions]

    try:
        result = await asyncio.to_thread(
            _compute_batch_explanations,
            inference_pipeline,
            shap_engine,
            raw_tx_list,
            req.top_k,
        )
    except Exception as exc:
        logger.error(f"Batch SHAP explanation failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch explanation calculation failed: {exc}",
        ) from exc

    return BatchExplainResponse(
        explanations=result["explanations"],
        total_transactions=result["total_transactions"],
        batch_latency_ms=result["batch_latency_ms"],
    )
