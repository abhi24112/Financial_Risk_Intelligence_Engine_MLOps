import logging

from shared import configure_logging

# configuration of logging
configure_logging(log_file="test_logging.log")

error_status = False

logging.info("Starting the logging test")
print(
    "Hello this is the logging unit test checks if the logging is running correct "
    "in cmd or in folder `logs/test_logging`"
)
logging.info("Output is correct printed")

if not error_status:
    logging.error(f"the error status is {error_status} value.")
else:
    logging.warning(f"the error status is {error_status} value.")
