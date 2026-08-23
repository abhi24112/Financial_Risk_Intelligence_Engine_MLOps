import logging

from pipelines.evaluation_pipeline import EvaluationPipeline
from pipelines.training_pipeline import TrainingPipeline
from shared.config_loader import load_config
from shared.logging.logging_config import configure_logging


def main():
    """
    Runs an automated experiment looping through multiple algorithms.
    Trains and evaluates each model, logging all metrics to MLflow side-by-side.
    """
    configure_logging(log_file="experiments.log")
    logger = logging.getLogger("ExperimentRunner")

    # Load the base tracking configuration
    base_config = load_config("model.yaml")

    models_to_test = ["xgboost", "lightgbm", "random_forest"]

    logger.info("=" * 50)
    logger.info(f"STARTING BATCH EXPERIMENT: {len(models_to_test)} Models")
    logger.info("=" * 50)

    results = {}

    for model_type in models_to_test:
        logger.info(f"\n---> Triggering Pipeline for: {model_type} <---")

        # 1. Dynamically build the configuration for this specific loop
        experiment_config = base_config.copy()
        experiment_config["tuning_state"] = "default"  # Tags it as 'xgboost_default' in MLflow
        experiment_config["model"] = {
            "model_type": model_type,
            # Empty dict means it will use the default parameters set in ModelTrainer
            "model_params": {},
        }

        # 2. Train the Model
        logger.info(f"Training {model_type}...")
        train_pipe = TrainingPipeline(experiment_config)
        train_res = train_pipe.run()

        if train_res.status != "success":
            logger.error(f"Training failed for {model_type}: {train_res.error}")
            continue

        # 3. Evaluate the Model (Automatically uses the run_id from training)
        logger.info(f"Evaluating {model_type}...")
        eval_pipe = EvaluationPipeline(experiment_config)
        eval_res = eval_pipe.run()

        if eval_res.status != "success":
            logger.error(f"Evaluation failed for {model_type}: {eval_res.error}")
            continue

        pr_auc = eval_res.metadata.get("test_pr_auc", 0.0)
        logger.info(f"[SUCCESS] {model_type.upper()} Finished! PR-AUC: {pr_auc:.4f}")
        results[model_type] = pr_auc

    # Print a summary leaderboard
    logger.info("\n==================================================")
    logger.info("[LEADERBOARD] EXPERIMENT LEADERBOARD (PR-AUC) [LEADERBOARD]")
    logger.info("==================================================")

    # Sort results highest to lowest
    sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)
    for rank, (model, score) in enumerate(sorted_results, 1):
        logger.info(f"{rank}. {model.ljust(15)} | PR-AUC: {score:.4f}")


if __name__ == "__main__":
    main()
