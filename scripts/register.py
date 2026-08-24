import argparse
import logging
import sys

from pipelines.registration_pipeline import RegistrationPipeline
from shared.config_loader import load_config
from shared.logging.logging_config import configure_logging


def main():
    parser = argparse.ArgumentParser(description="Run the Model Registration Pipeline.")
    parser.add_argument(
        "--config",
        type=str,
        default="model.yaml",
        help="Name of the configuration file in configs/ (default: model.yaml)",
    )
    args = parser.parse_args()

    configure_logging(log_file="register_script.log")
    logger = logging.getLogger("RegisterScript")

    logger.info(f"Loading configuration from {args.config}...")
    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)

    logger.info("Initializing Registration Pipeline...")
    pipeline = RegistrationPipeline(config)

    logger.info("Executing Pipeline...")
    result = pipeline.run()

    if result.status == "success":
        logger.info("=" * 50)
        logger.info("[SUCCESS] REGISTRATION COMPLETED SUCCESSFULLY [SUCCESS]")
        logger.info("=" * 50)

        metadata = result.metadata
        logger.info(f"Action Taken: {metadata.get('action').upper()}")  # type: ignore

        if metadata.get("action") == "promoted":
            logger.info(f"New Production V:  v{metadata.get('new_production_version')}")
            logger.info(f"Challenger PR-AUC: {metadata.get('challenger_pr_auc'):.4f}")
            if metadata.get("champion_pr_auc", -1.0) != -1.0:
                logger.info(f"Old Champion PR-AUC: {metadata.get('champion_pr_auc'):.4f}")
            else:
                logger.info("Old Champion PR-AUC: N/A (First Model)")
        else:
            logger.info(f"Retained Champion: v{metadata.get('champion_version')}")
            logger.info(f"Champion PR-AUC:   {metadata.get('champion_pr_auc'):.4f}")
            logger.info(f"Challenger PR-AUC: {metadata.get('challenger_pr_auc'):.4f}")

        logger.info("==================================================")
    else:
        logger.error("[FAILED] REGISTRATION FAILED [FAILED]")
        logger.error(f"Error: {result.error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
