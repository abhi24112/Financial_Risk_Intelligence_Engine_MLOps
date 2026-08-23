import argparse
import logging
import sys

from pipelines.evaluation_pipeline import EvaluationPipeline
from shared.config_loader import load_config
from shared.logging.logging_config import configure_logging


def main():
    parser = argparse.ArgumentParser(description="Run the Model Evaluation Pipeline.")
    parser.add_argument(
        "--config",
        type=str,
        default="model.yaml",
        help="Name of the configuration file in configs/ (default: model.yaml)",
    )
    args = parser.parse_args()

    configure_logging(log_file="evaluate_script.log")
    logger = logging.getLogger("EvaluateScript")

    logger.info(f"Loading configuration from {args.config}...")
    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)

    logger.info("Initializing Evaluation Pipeline...")
    pipeline = EvaluationPipeline(config)

    logger.info("Executing Pipeline...")
    result = pipeline.run()

    if result.status == "success":
        logger.info("==================================================")
        logger.info("[SUCCESS] EVALUATION COMPLETED SUCCESSFULLY [SUCCESS]")
        logger.info("==================================================")
        logger.info(f"PR-AUC (Primary Metric): {result.metadata.get('test_pr_auc'):.4f}")
        logger.info(f"ROC-AUC:                 {result.metadata.get('test_roc_auc'):.4f}")
        logger.info(f"F1-Score:                {result.metadata.get('test_f1_score'):.4f}")
        logger.info(f"Recall (Fraud Caught):   {result.metadata.get('test_recall'):.4f}")
        logger.info("--- Confusion Matrix ---")
        logger.info(f"True Negatives (Safe correctly allowed): {result.metadata.get('test_true_negatives')}")
        logger.info(f"False Positives (Safe wrongly blocked):  {result.metadata.get('test_false_positives')}")
        logger.info(f"False Negatives (Fraud missed):          {result.metadata.get('test_false_negatives')}")
        logger.info(f"True Positives (Fraud caught):           {result.metadata.get('test_true_positives')}")
        logger.info("==================================================")
    else:
        logger.error("[FAILED] EVALUATION FAILED [FAILED]")
        logger.error(f"Error: {result.error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
