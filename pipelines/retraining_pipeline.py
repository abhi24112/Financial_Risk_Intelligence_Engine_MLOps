import json
import os
from typing import Any

from pipelines.base_pipeline import BasePipeline
from pipelines.evaluation_pipeline import EvaluationPipeline
from pipelines.registration_pipeline import RegistrationPipeline
from pipelines.training_pipeline import TrainingPipeline
from shared import configure_logging

configure_logging(log_file="retraining.log")


class RetrainingPipeline(BasePipeline):
    """
    Automated Retraining & Model Promotion Orchestrator.

    Triggered either:
      1. Automatically upon Data Drift detection (via MonitoringPipeline).
      2. By scheduled cron/Airflow DAG.
      3. Manually via CLI or API.

    Orchestration Flow:
      [Check Drift / Trigger] ➔ [Train Challenger] ➔ [Evaluate Metrics] ➔ [Champion vs Challenger Showdown]
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.force_retrain = self.config.get("force", False)
        self.trigger_source = self.config.get("trigger", "drift_detected")
        self.model_type = self.config.get("model_type", "lightgbm")

    def _should_retrain(self) -> tuple[bool, str]:
        """Evaluates whether retraining conditions are met."""
        if self.force_retrain:
            return True, "Forced manual retraining requested (--force)."

        # Check latest monitoring report if available
        monitoring_report_path = os.path.join("dataset", "reports", "monitoringpipeline_report.json")
        if os.path.exists(monitoring_report_path):
            try:
                with open(monitoring_report_path, encoding="utf-8") as f:
                    report = json.load(f)
                    drift_detected = report.get("metadata", {}).get("dataset_drift_detected", False)
                    drift_share = report.get("metadata", {}).get("drift_share", 0.0)
                    if drift_detected:
                        return True, f"Data drift detected ({drift_share:.1%} of columns drifted > threshold)."
                    return (
                        False,
                        f"Monitoring report checked: No data drift detected ({drift_share:.1%} drifted <= threshold). Retraining not needed.",
                    )
            except Exception as e:
                self.logger.warning(f"Could not parse monitoring report: {e}. Falling back to default trigger check.")
        else:
            self.logger.info(f"No monitoring report found at '{monitoring_report_path}'.")

        if self.trigger_source in ["scheduled", "manual"]:
            return True, f"Retraining triggered by {self.trigger_source} event."

        return False, "No data drift detected and force=False. Retraining skipped."

    def _execute(self) -> dict[str, Any]:
        self.logger.info("Starting Retraining Pipeline evaluation...")

        # 1. Check if retraining is necessary
        should_run, reason = self._should_retrain()
        self.logger.info(f"Retraining decision: {reason}")

        if not should_run:
            return {
                "metadata": {
                    "action": "skipped",
                    "reason": reason,
                }
            }

        # 2. Stage 1: Train Candidate Model (Challenger)
        self.logger.info(f"==> Stage 1: Training candidate model ({self.model_type})...")
        trainer = TrainingPipeline(config={"model_type": self.model_type})
        train_result = trainer.run()

        if train_result.status != "success":
            raise RuntimeError(f"Training stage failed: {train_result.error}")

        challenger_run_id = train_result.metadata.get("mlflow_run_id")
        self.logger.info(f"Candidate model trained successfully. MLflow Run ID: {challenger_run_id}")

        # 3. Stage 2: Evaluate Candidate Model
        self.logger.info("==> Stage 2: Evaluating candidate model on test dataset...")
        evaluator = EvaluationPipeline()
        eval_result = evaluator.run()

        if eval_result.status != "success":
            raise RuntimeError(f"Evaluation stage failed: {eval_result.error}")

        metrics = eval_result.metadata.get("metrics", {})
        challenger_pr_auc = metrics.get("PR_AUC", 0.0)
        self.logger.info(f"Evaluation complete. Challenger PR-AUC: {challenger_pr_auc:.4f}")

        # 4. Stage 3: Champion vs Challenger Showdown & Promotion
        self.logger.info("==> Stage 3: Running Champion vs Challenger Model Registration...")
        registrar = RegistrationPipeline(config={"target_run_id": challenger_run_id})
        reg_result = registrar.run()

        if reg_result.status != "success":
            raise RuntimeError(f"Registration stage failed: {reg_result.error}")

        reg_metadata = reg_result.metadata
        action = reg_metadata.get("action", "none")

        self.logger.info(
            f"Retraining Pipeline completed! Action: {action.upper()} | "
            f"Challenger Score: {challenger_pr_auc:.4f} vs Champion: {reg_metadata.get('champion_pr_auc', -1.0):.4f}"
        )

        return {
            "artifacts": {
                "model_path": train_result.metadata.get("local_model_path"),
            },
            "metadata": {
                "trigger_reason": reason,
                "challenger_run_id": challenger_run_id,
                "challenger_pr_auc": challenger_pr_auc,
                "champion_pr_auc": reg_metadata.get("champion_pr_auc"),
                "promotion_action": action,
                "new_production_version": reg_metadata.get("new_production_version"),
            },
        }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Automated Retraining Pipeline")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force retraining regardless of drift report status",
    )
    parser.add_argument(
        "--trigger",
        type=str,
        default="drift_detected",
        choices=["drift_detected", "scheduled", "manual"],
        help="Trigger source for retraining",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="lightgbm",
        choices=["lightgbm", "xgboost", "random_forest"],
        help="Model type to train",
    )
    args = parser.parse_args()

    pipeline = RetrainingPipeline(
        config={
            "force": args.force,
            "trigger": args.trigger,
            "model_type": args.model,
        }
    )
    result = pipeline.run()
    print("\n--- Retraining Pipeline Result ---")
    print("Status:", result.status)
    print("Metadata:", json.dumps(result.metadata, indent=2))
