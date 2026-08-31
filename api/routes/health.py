from datetime import datetime

from fastapi import APIRouter, Request, status

from api.schemas import HealthResponse

router = APIRouter(tags=["Health & Telemetry"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Liveness Probe",
    description="Returns OK if the HTTP service is running and responsive.",
)
async def health_check(request: Request) -> HealthResponse:
    inference_pipeline = getattr(request.app.state, "inference_pipeline", None)
    model_loaded = inference_pipeline is not None and getattr(inference_pipeline, "model", None) is not None

    redis_connected = False
    if inference_pipeline and getattr(inference_pipeline, "feature_store", None):
        try:
            client = inference_pipeline.feature_store.client
            redis_connected = client.ping() if client else False
        except Exception:
            redis_connected = False

    return HealthResponse(
        status="healthy" if model_loaded else "degraded",
        model_loaded=model_loaded,
        redis_connected=redis_connected,
        timestamp=datetime.utcnow().isoformat() + "Z",
        version="1.0.0",
    )


@router.get(
    "/ready",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Readiness Probe",
    description="Returns OK only when both the ML model is preloaded and Redis Feature Store is connected.",
)
async def readiness_check(request: Request) -> HealthResponse:
    inference_pipeline = getattr(request.app.state, "inference_pipeline", None)
    model_loaded = inference_pipeline is not None and getattr(inference_pipeline, "model", None) is not None

    redis_connected = False
    if inference_pipeline and getattr(inference_pipeline, "feature_store", None):
        try:
            client = inference_pipeline.feature_store.client
            redis_connected = client.ping() if client else False
        except Exception:
            redis_connected = False

    is_ready = model_loaded and redis_connected
    return HealthResponse(
        status="ready" if is_ready else "not_ready",
        model_loaded=model_loaded,
        redis_connected=redis_connected,
        timestamp=datetime.utcnow().isoformat() + "Z",
        version="1.0.0",
    )
