import uvicorn

from shared.config_loader import load_config
from shared.logger import get_logger

logger = get_logger("main")


def main():
    try:
        config = load_config("api.yaml")
        server_cfg = config.get("server", {})
    except Exception as e:
        logger.warning(f"Could not load api.yaml ({e}). Using default server config.")
        server_cfg = {"host": "0.0.0.0", "port": 8000, "reload": False, "workers": 1}

    host = server_cfg.get("host", "0.0.0.0")
    port = server_cfg.get("port", 8000)
    reload = server_cfg.get("reload", False)
    workers = server_cfg.get("workers", 1)

    logger.info(f"Starting Financial Risk Intelligence Engine API on http://{host}:{port}")
    print("\n=======================================================")
    print(">> Financial Risk Intelligence Engine Serving Layer")
    print(f">> API Server:   http://localhost:{port}")
    print(f">> Swagger Docs: http://localhost:{port}/docs")
    print(f">> Web UI:      http://localhost:{port}/ui")
    print("=======================================================\n")

    uvicorn.run(
        "api.app:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers,
    )


if __name__ == "__main__":
    main()
