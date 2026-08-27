import json
import os
from typing import Any

import joblib
import mlflow
import pandas as pd

from ml.evaluation.evaluator import ModelEvaluator
from pipelines.base_pipeline import BasePipeline
from shared import configure_logging, constants

configure_logging(log_file="evaluation.log")


class EvaluationPipeline(BasePipeline):
    """
    Evaluates a trained model on the unseen test dataset.
    Calculates critical business metrics (PR-AUC, Recall, F1) and logs
    them directly into the SAME MLflow run that created the model.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.target_col = constants.TARGET_FEATURE

        # Setup MLflow Tracking
        mlflow_uri = self.config.get("mlflow_tracking_uri", "sqlite:///mlflow.db")
        if mlflow_uri:
            mlflow.set_tracking_uri(mlflow_uri)

    def _get_training_report(self) -> dict[str, Any]:
        report_path = os.path.join("dataset", "reports", "trainingpipeline_report.json")
        if not os.path.exists(report_path):
            raise FileNotFoundError(f"Training report not found at {report_path}. Run TrainingPipeline first.")
        with open(report_path) as f:
            return json.load(f)

    def _execute(self) -> dict[str, Any]:
        # 1. Fetch info from the Training phase
        training_report = self._get_training_report()
        model_path = training_report.get("metadata", {}).get("local_model_path")
        run_id = training_report.get("metadata", {}).get("mlflow_run_id")

        if not model_path or not os.path.exists(model_path):
            raise FileNotFoundError(f"Trained model not found at {model_path}.")

        self.logger.info(f"Loading model from {model_path}")
        model = joblib.load(model_path)

        # 2. Load the completely unseen Test dataset
        processed_dir = getattr(constants, "PROCESSED_DATASET_DIR", os.path.join("dataset", "processed"))
        test_path = os.path.join(processed_dir, constants.TEST_DATA_FILE)

        self.logger.info(f"Loading test data from {test_path}")
        test_df = pd.read_parquet(test_path)

        # 3. Strip features just like in Training
        drop_cols = [
            self.target_col,
            "TransactionID",
            "uid_card",
            "uid_card_email",
            "uid_card_device",
            "TransactionDT",
        ]
        test_drop = [c for c in drop_cols if c in test_df.columns]

        X_test = test_df.drop(columns=test_drop)
        y_test = test_df[self.target_col]

        # 4. Generate Predictions & Calculate strict business metrics
        evaluator = ModelEvaluator()
        metrics = evaluator.evaluate(model, X_test, y_test)

        # 6. Push metrics to the exact same MLflow run
        if run_id:
            self.logger.info(f"Resuming MLflow Run ID {run_id} to log metrics.")
            with mlflow.start_run(run_id=run_id):
                mlflow.log_metrics(metrics)
        else:
            self.logger.warning("No MLflow run_id found. Metrics not logged to MLflow.")

        self.logger.info(f"Evaluation complete. PR-AUC: {metrics.get('test_pr_auc', 0.0):.4f} | Recall: {metrics.get('test_recall', 0.0):.4f}")

        # 7. Return to BasePipeline to generate evaluationpipeline_report.json
        return {"metadata": metrics}
