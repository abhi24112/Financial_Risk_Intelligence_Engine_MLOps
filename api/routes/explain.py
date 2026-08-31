import asyncio
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from api.schemas import ExplainRequest, ExplainResponse
from explainability.shap_engine import SHAPEngine
from shared.logger import get_logger

logger = get_logger("api_explain")
router = APIRouter(tags=["Explainability Engine"])


def _compute_single_explanation(inference_pipeline: Any, shap_engine: SHAPEngine, raw_tx: dict[str, Any], top_k: int) -> dict[str, Any]:
    """
    Synchronous helper executed in worker thread for SHAP explanation computation.
    """
    start_time = time.perf_counter()

    # 1. Get prediction
    pred_res = inference_pipeline.predict(raw_tx)

    # 2. Build preprocessed numeric dataframe
    df_features = inference_pipeline._build_features(raw_tx)

    # 3. Extract estimator
    pipeline = inference_pipeline.model
    if hasattr(pipeline, "named_steps") and "model" in pipeline.named_steps:
        estimator = pipeline.named_steps["model"]
    else:
        estimator = pipeline

    tx_id = raw_tx.get("TransactionID", "tx_current")

    # 4. Generate SHAP explanation
    explanations = shap_engine.explain(model=estimator, X_sample=df_features, X_shap=df_features, tx_ids=[tx_id], top_k=top_k)

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
        # Offload heavy SHAP computation to worker thread to protect the event loop
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
