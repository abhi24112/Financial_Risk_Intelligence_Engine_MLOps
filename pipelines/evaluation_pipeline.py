import json
import os
from typing import Any

import joblib
import mlflow
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

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
        """Reads the JSON report from the TrainingPipeline to find the model path and Run ID."""
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

        # 4. Generate Predictions
        self.logger.info("Generating predictions on test set...")
        y_prob = model.predict_proba(X_test)[:, 1]
        y_pred = model.predict(X_test)

        # 5. Calculate strict business metrics (Cost-Sensitive)
        self.logger.info("Calculating MLOps evaluation metrics...")
        roc_auc = float(roc_auc_score(y_test, y_prob))
        pr_auc = float(average_precision_score(y_test, y_prob))
        f1 = float(f1_score(y_test, y_pred))
        recall = float(recall_score(y_test, y_pred))
        precision = float(precision_score(y_test, y_pred))

        # Confusion Matrix breakdown
        cm = confusion_matrix(y_test, y_pred)
        tn, fp, fn, tp = int(cm[0][0]), int(cm[0][1]), int(cm[1][0]), int(cm[1][1])

        metrics = {
            "test_roc_auc": roc_auc,
            "test_pr_auc": pr_auc,
            "test_f1_score": f1,
            "test_recall": recall,
            "test_precision": precision,
            "test_true_negatives": tn,
            "test_false_positives": fp,
            "test_false_negatives": fn,
            "test_true_positives": tp,
        }

        # 6. Push metrics to the exact same MLflow run
        if run_id:
            self.logger.info(f"Resuming MLflow Run ID {run_id} to log metrics.")
            with mlflow.start_run(run_id=run_id):
                mlflow.log_metrics(metrics)
        else:
            self.logger.warning("No MLflow run_id found. Metrics not logged to MLflow.")

        self.logger.info(f"Evaluation complete. PR-AUC: {pr_auc:.4f} | Recall: {recall:.4f}")

        # 7. Return to BasePipeline to generate evaluationpipeline_report.json
        return {"metadata": metrics}
