from typing import Any

import mlflow
from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient

from pipelines.base_pipeline import BasePipeline
from shared import configure_logging

configure_logging(log_file="registration.log")


class RegistrationPipeline(BasePipeline):
    """
    Promotes the best tuned model to the MLflow Model Registry.
    Implements a Champion/Challenger strategy based on PR-AUC.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.experiment_name = self.config.get("experiment_name", "Fraud_Detection_Training")
        self.model_name = self.config.get("registered_model_name", "fraud_risk_model")

        mlflow_uri = self.config.get("mlflow_tracking_uri", "sqlite:///mlflow.db")
        if mlflow_uri:
            mlflow.set_tracking_uri(mlflow_uri)

        self.client = MlflowClient()

    def _execute(self) -> dict[str, Any]:
        self.logger.info("Starting Champion/Challenger Model Registration...")

        # 1. Find the absolute best run (Challenger)
        experiment = self.client.get_experiment_by_name(self.experiment_name)
        if not experiment:
            raise ValueError(f"Experiment {self.experiment_name} not found in MLflow.")

        target_run_id = self.config.get("target_run_id")

        if target_run_id:
            self.logger.info(f"Manual override: Fetching specific Run ID {target_run_id}")
            best_run = self.client.get_run(target_run_id)
        else:
            self.logger.info("Auto-selecting best run based on PR-AUC...")
            # Search for the run with the highest PR-AUC
            runs = self.client.search_runs(experiment_ids=[experiment.experiment_id], order_by=["metrics.test_pr_auc DESC"], max_results=1)

            if not runs:
                raise ValueError(f"No runs found in experiment {self.experiment_name}.")
            best_run = runs[0]
        challenger_run_id = best_run.info.run_id
        challenger_score = best_run.data.metrics.get("test_pr_auc", 0.0)

        self.logger.info(f"Challenger Run ID: {challenger_run_id} | PR-AUC: {challenger_score:.4f}")

        # 2. Check for an existing Champion
        champion_version = None
        champion_score = -1.0

        try:
            versions = self.client.get_latest_versions(self.model_name, stages=["Production"])
            if versions:
                champion_version = versions[0]
                if champion_version.run_id is not None:
                    champion_run = self.client.get_run(champion_version.run_id)
                    champion_score = champion_run.data.metrics.get("test_pr_auc", -1.0)
                    self.logger.info(f"Current Champion Version: {champion_version.version} | PR-AUC: {champion_score:.4f}")
                else:
                    self.logger.warning(
                        f"Production version {champion_version.version} for model '{self.model_name}' has no associated run ID."
                        "skipping champion score check."
                    )

            else:
                self.logger.info(f"No active 'Production' version found for model '{self.model_name}'.")
        except MlflowException:
            self.logger.info(f"Model '{self.model_name}' does not exist in registry yet. It will be created.")

        # 3. The Showdown
        result_metadata = {
            "challenger_run_id": challenger_run_id,
            "challenger_pr_auc": challenger_score,
            "champion_pr_auc": champion_score,
            "action": "none",
        }

        is_manual_override = target_run_id is not None

        if champion_version is None or challenger_score > champion_score or is_manual_override:
            if is_manual_override and champion_version is not None and challenger_score <= champion_score:
                self.logger.info(f"Manual Override: Forcing promotion of {target_run_id} despite lower PR-AUC.")
            else:
                self.logger.info("Challenger wins! (or no champion exists). Registering...")

            # Register the model
            model_uri = f"runs:/{challenger_run_id}/model"
            mv = mlflow.register_model(model_uri, self.model_name)

            self.logger.info(f"Transitioning Version {mv.version} to 'Production'...")
            self.client.transition_model_version_stage(name=self.model_name, version=mv.version, stage="Production", archive_existing_versions=True)

            result_metadata["action"] = "promoted"
            result_metadata["new_production_version"] = mv.version
        else:
            self.logger.info(f"Champion retains title! Champion score ({champion_score:.4f}) >= Challenger ({challenger_score:.4f})")

            result_metadata["action"] = "rejected"
            result_metadata["champion_version"] = champion_version.version

        return {"metadata": result_metadata}
