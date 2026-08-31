import logging


def get_logger(name: str | None = None) -> logging.Logger:
    """
    Returns a configured structured logger.
    """
    return logging.getLogger(name or "risk_engine")
