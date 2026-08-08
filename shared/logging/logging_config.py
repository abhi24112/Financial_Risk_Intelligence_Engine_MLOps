import logging
import os
import sys

from shared.constants import constants


def configure_logging(level=logging.INFO, log_file=None):

    # Making logs/ directory
    os.makedirs(constants.LOG_DIR, exist_ok=True)

    handlers = [logging.StreamHandler(sys.stdout)]

    if log_file:
        handlers.append(logging.FileHandler(f"{constants.LOG_DIR}/" + log_file))
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=handlers,
        force=True,
    )
