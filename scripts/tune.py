import logging

import optuna

from pipelines.evaluation_pipeline import EvaluationPipeline
from pipelines.training_pipeline import TrainingPipeline
from shared.config_loader import load_config
from shared.logging.logging_config import configure_logging


def objective(trial, base_config, model_type):
    """
    Optuna objective function for tuning ANY of our 3 models.
    """
    experiment_config = base_config.copy()
    experiment_config["tuning_state"] = f"{model_type}_tuned_trial_{trial.number}"
    model_params = {}

    # 1. Define mathematically sound search spaces for each architecture
    if model_type == "xgboost":
        model_params = {
            "max_depth": trial.suggest_int("max_depth", 3, 9),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 50, 300),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
        }
    elif model_type == "lightgbm":
        model_params = {
            "max_depth": trial.suggest_int("max_depth", 3, 12),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 50, 300),
            "num_leaves": trial.suggest_int("num_leaves", 20, 150),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        }
    elif model_type == "random_forest":
        model_params = {
            "max_depth": trial.suggest_int("max_depth", 5, 20),
            "n_estimators": trial.suggest_int("n_estimators", 50, 200),
            "min_samples_split": trial.suggest_int("min_samples_split", 2, 10),
            "n_jobs": -1,
        }
    else:
        raise ValueError(f"Unknown model_type: {model_type}")

    experiment_config["model"] = {
        "model_type": model_type,
        "model_params": model_params,
    }

    # 2. Train
    train_pipe = TrainingPipeline(experiment_config)
    train_res = train_pipe.run()
    if train_res.status != "success":
        raise optuna.exceptions.TrialPruned()

    # 3. Evaluate
    eval_pipe = EvaluationPipeline(experiment_config)
    eval_res = eval_pipe.run()
    if eval_res.status != "success":
        raise optuna.exceptions.TrialPruned()

    # 4. Return PR-AUC for Optuna to optimize
    return eval_res.metadata.get("test_pr_auc", 0.0)


def main():
    configure_logging(log_file="tune.log")
    logger = logging.getLogger("TuningScript")

    # Silence Optuna's default console spam
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    # Silence ONLY the inner pipelines so our tqdm progress bar stays on ONE line!
    # (Their logs will still safely save to their respective .log and .json files)
    logging.getLogger("TrainingPipeline").setLevel(logging.WARNING)
    logging.getLogger("EvaluationPipeline").setLevel(logging.WARNING)
    logging.getLogger("ml.training.trainer").setLevel(logging.WARNING)

    base_config = load_config("model.yaml")

    models_to_tune = ["xgboost", "lightgbm", "random_forest"]
    num_trials = 40  # You can change this to 20 or 50 later

    for model_type in models_to_tune:
        logger.info("\n")
        logger.info("=" * 50)
        logger.info(f"[TUNING] STARTING {model_type.upper()} ({num_trials} TRIALS) [TUNING]")
        logger.info("=" * 50)

        study = optuna.create_study(direction="maximize", study_name=f"Fraud_{model_type.capitalize()}_Tuning")

        from tqdm import tqdm

        # We create a simple wrapper function to pass our extra arguments.
        def optuna_wrapper(trial, current_model=model_type):
            return objective(trial, base_config, current_model)

        try:
            # Create a progress bar that updates via a callback after each trial
            with tqdm(total=num_trials, desc=f"Tuning {model_type.upper()}") as pbar:

                def tqdm_callback(study, trial):
                    pbar.update(1)

                study.optimize(optuna_wrapper, n_trials=num_trials, callbacks=[tqdm_callback])
        except KeyboardInterrupt:
            logger.info("Tuning interrupted by user. Moving to next model...")

        logger.info(f"--> Best PR-AUC Score for {model_type.upper()}: {study.best_value:.4f}")
        logger.info(f"--> Best Parameters: {study.best_params}")


if __name__ == "__main__":
    main()
