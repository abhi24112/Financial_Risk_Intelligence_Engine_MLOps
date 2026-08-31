import os

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["User Interface"])


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
async def serve_ui() -> HTMLResponse:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html_path = os.path.join(base_dir, "static", "index.html")

    if not os.path.exists(html_path):
        return HTMLResponse("<h3>Adaptive Financial Risk Intelligence Engine UI</h3><p>Static index.html not found.</p>")

    with open(html_path, encoding="utf-8") as f:
        content = f.read()

    return HTMLResponse(content=content)
