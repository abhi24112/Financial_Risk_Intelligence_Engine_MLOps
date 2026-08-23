import argparse
import logging
import sys

from pipelines.training_pipeline import TrainingPipeline
from shared.config_loader import load_config
from shared.logging.logging_config import configure_logging


def main():
    # Setup simple argument parsing in case we want to specify a different config later
    parser = argparse.ArgumentParser(description="Run the Model Training Pipeline.")
    parser.add_argument(
        "--config",
        type=str,
        default="model.yaml",
        help="Name of the configuration file in configs/ (default: model.yaml)",
    )
    args = parser.parse_args()
    print("ouput:", args)

    # Configure logging for the console so we can watch it run
    configure_logging(log_file="train_script.log")
    logger = logging.getLogger("TrainScript")

    logger.info(f"Loading configuration from {args.config}...")
    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)

    logger.info("Initializing Training Pipeline...")
    pipeline = TrainingPipeline(config)

    logger.info("Executing Pipeline...")
    result = pipeline.run()

    # Print the final result nicely to the terminal
    if result.status == "success":
        logger.info("==================================================")
        logger.info("[SUCCESS] TRAINING COMPLETED SUCCESSFULLY [SUCCESS]")
        logger.info("==================================================")
        logger.info(f"Model Type:    {result.metadata.get('model_type')}")
        logger.info(f"MLflow Run ID: {result.metadata.get('mlflow_run_id')}")
        logger.info(f"Train Rows:    {result.metadata.get('train_rows')}")
        logger.info(f"Val Rows:      {result.metadata.get('val_rows')}")
        logger.info(f"Features:      {result.metadata.get('features_used')}")
        logger.info(f"Saved Path:    {result.metadata.get('local_model_path')}")
        logger.info("==================================================")
    else:
        logger.error("[FAILED] TRAINING FAILED [FAILED]")
        logger.error(f"Error: {result.error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
