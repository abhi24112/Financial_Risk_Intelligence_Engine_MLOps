from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.middleware.timing import RequestTimingAndIDMiddleware
from api.routes import explain_router, health_router, predict_router, ui_router
from explainability.shap_engine import SHAPEngine
from pipelines.inference_pipeline import InferencePipeline
from shared.config_loader import load_config
from shared.logger import get_logger

logger = get_logger("api_app")


def _get_api_config() -> dict[str, Any]:
    """Loads api.yaml or provides sensible production defaults."""
    try:
        return load_config("api.yaml")
    except Exception:
        return {
            "app": {
                "title": "Adaptive Financial Risk Intelligence Engine",
                "description": "Real-time, low-latency financial transaction risk assessment & explainability API",
                "version": "1.0.0",
                "docs_url": "/docs",
                "redoc_url": "/redoc",
            },
            "cors": {
                "allow_origins": ["*"],
                "allow_credentials": True,
                "allow_methods": ["*"],
                "allow_headers": ["*"],
            },
        }


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application Lifespan Context:
    - Pre-loads the Champion Model into memory on startup (ensuring <100ms inference).
    - Connects to the Redis Feature Store.
    - Pre-initializes the SHAP TreeExplainer.
    - Handles clean shutdown.
    """
    logger.info("Initializing Financial Risk Intelligence Engine serving layer...")

    try:
        # Load the inference pipeline (which warms up the Champion model and Redis)
        app.state.inference_pipeline = InferencePipeline()
        logger.info("Inference Pipeline loaded into app.state successfully.")
    except Exception as e:
        logger.error(f"Failed to load InferencePipeline during startup: {e}", exc_info=True)
        app.state.inference_pipeline = None

    try:
        # Pre-initialize SHAP explanation engine
        app.state.shap_engine = SHAPEngine()
        logger.info("SHAP Explainability Engine initialized.")
    except Exception as e:
        logger.warning(f"SHAP engine initialization warning: {e}")
        app.state.shap_engine = None

    yield

    logger.info("Shutting down Financial Risk Intelligence Engine API.")


def create_app() -> FastAPI:
    """FastAPI Application Factory."""
    config = _get_api_config()
    app_cfg = config.get("app", {})
    cors_cfg = config.get("cors", {})

    app = FastAPI(
        title=app_cfg.get("title", "Adaptive Financial Risk Intelligence Engine"),
        description=app_cfg.get("description", "High-throughput real-time risk scoring API"),
        version=app_cfg.get("version", "1.0.0"),
        docs_url=app_cfg.get("docs_url", "/docs"),
        redoc_url=app_cfg.get("redoc_url", "/redoc"),
        lifespan=lifespan,
    )

    # 1. Add CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_cfg.get("allow_origins", ["*"]),
        allow_credentials=cors_cfg.get("allow_credentials", True),
        allow_methods=cors_cfg.get("allow_methods", ["*"]),
        allow_headers=cors_cfg.get("allow_headers", ["*"]),
    )

    # 2. Add Custom Request Timing & ID Middleware
    app.add_middleware(RequestTimingAndIDMiddleware)

    # 3. Global Exception Handlers
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, "request_id", None)
        logger.warning(f"[{request_id}] Validation error on {request.url.path}: {exc.errors()}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "Unprocessable Entity",
                "message": "Input validation failed. Please check field types and required values.",
                "details": exc.errors(),
                "request_id": request_id,
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.detail,
                "status_code": exc.status_code,
                "request_id": request_id,
            },
        )

    # 4. Include Modular Routers
    app.include_router(ui_router)
    app.include_router(health_router)
    app.include_router(predict_router)
    app.include_router(explain_router)

    return app


# Module-level app instance for ASGI servers like uvicorn
app = create_app()
