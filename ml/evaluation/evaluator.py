import logging
from typing import Any

import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


class ModelEvaluator:
    """
    Core ML logic for calculating model performance metrics.
    Abstracts away the scikit-learn metric calculation from the pipeline orchestration.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def evaluate(self, model: Any, X_test: pd.DataFrame, y_test: pd.Series) -> dict[str, float]:
        """
        Generates predictions and computes classification metrics.
        Returns a dictionary of metrics ready for MLflow or reporting.
        """
        self.logger.info("Generating predictions on test set...")

        # Determine probability vs absolute predictions
        if hasattr(model, "predict_proba"):
            y_prob = model.predict_proba(X_test)[:, 1]
        else:
            # Fallback for models without predict_proba
            y_prob = model.predict(X_test)

        y_pred = model.predict(X_test)

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

        self.logger.info(f"Evaluation complete. PR-AUC: {pr_auc:.4f} | Recall: {recall:.4f}")
        return metrics
