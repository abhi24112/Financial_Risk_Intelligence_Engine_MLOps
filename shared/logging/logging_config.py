import logging
import os
import sys

from shared.constants import constants


def configure_logging(level=logging.INFO, log_file=None):
    """
    Configures root logging safely. Prevents recursive loops when executed inside
    frameworks like Airflow where sys.stdout is redirected to a StreamLogWriter.
    """
    # Create logs/ directory safely
    os.makedirs(constants.LOG_DIR, exist_ok=True)

    handlers: list[logging.Handler] = []

    # Detect if sys.stdout is redirected by Airflow or if running inside Airflow
    is_airflow = "AIRFLOW_HOME" in os.environ or "AIRFLOW_CONFIG" in os.environ or sys.stdout.__class__.__name__ == "StreamLogWriter"

    if not is_airflow:
        handlers.append(logging.StreamHandler(sys.stdout))

    if log_file:
        file_path = os.path.join(constants.LOG_DIR, log_file)
        handlers.append(logging.FileHandler(file_path))

    if handlers:
        # Avoid force=True in Airflow to prevent wiping Airflow's internal handlers
        logging.basicConfig(
            level=level,
            format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            handlers=handlers,
            force=not is_airflow,
        )
