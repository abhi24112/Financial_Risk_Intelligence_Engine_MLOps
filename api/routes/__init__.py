from api.routes.explain import router as explain_router
from api.routes.health import router as health_router
from api.routes.predict import router as predict_router
from api.routes.ui import router as ui_router

__all__ = ["health_router", "predict_router", "explain_router", "ui_router"]
