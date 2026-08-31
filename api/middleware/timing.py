import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from shared.logger import get_logger

logger = get_logger("api_timing")


class RequestTimingAndIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that:
    1. Injects a unique X-Request-ID for distributed request tracing.
    2. Measures total server-side latency and attaches X-Response-Time-Ms header.
    3. Logs structured request execution metrics.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate or capture incoming request correlation ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"[{request_id}] {request.method} {request.url.path} failed with unhandled exception: {exc} (took {duration_ms:.2f}ms)")
            raise exc

        duration_ms = (time.perf_counter() - start_time) * 1000

        # Inject headers into outgoing response
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"

        # Structured request logging
        logger.info(f"[{request_id}] {request.method} {request.url.path} -> status {response.status_code} ({duration_ms:.2f}ms)")

        return response
