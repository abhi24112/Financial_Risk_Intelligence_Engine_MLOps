import json
import os
from typing import Any

import mlflow
import mlflow.sklearn as mlflow_sklearn
import pandas as pd
from mlflow.tracking import MlflowClient

from pipelines.base_pipeline import BasePipeline
from shared import configure_logging, constants

configure_logging(log_file="explainability.log")


class ExplainabilityPipeline(BasePipeline):
    """
    Decoupled Explainability Engine using SHAP.
    Loads the registered champion model, runs SHAP on a batch of transactions,
    and maps the raw SHAP values to analyst-readable reasons.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.model_name = self.config.get("registered_model_name", "fraud_risk_model")

        mlflow_uri = self.config.get("mlflow_tracking_uri", "sqlite:///mlflow.db")
        if mlflow_uri:
            mlflow.set_tracking_uri(mlflow_uri)

        self.sample_size = self.config.get("sample_size", 100)  # limit for speed

    def _execute(self) -> dict[str, Any]:
        self.logger.info("Starting Explainability Pipeline (SHAP)...")

        # 1. Load Data
        processed_dir = constants.PROCESSED_DATASET_DIR
        test_path = os.path.join(processed_dir, constants.TEST_DATA_FILE)

        if not os.path.exists(test_path):
            raise FileNotFoundError(f"Test data not found at {test_path}")

        self.logger.info(f"Loading test dataset from {test_path}")
        df = pd.read_parquet(test_path)

        # We only need features, drop target and IDs if they exist
        drop_cols = [
            constants.TARGET_FEATURE,
            "TransactionID",
            "uid_card",
            "uid_card_email",
            "uid_card_device",
            "TransactionDT",
        ]
        drop_cols = [c for c in drop_cols if c in df.columns]
        X = df.drop(columns=drop_cols)

        # Downsample for speed in this batch job
        if len(X) > self.sample_size:
            X_sample = X.sample(n=self.sample_size, random_state=42)
            if "TransactionID" in df.columns:
                tx_ids = df.loc[X_sample.index, "TransactionID"].values
            else:
                tx_ids = X_sample.index
        else:
            X_sample = X
            tx_ids = df["TransactionID"].values if "TransactionID" in df.columns else X_sample.index

        # 2. Load the Production model from MLflow Registry
        model_uri = f"models:/{self.model_name}/Production"
        self.logger.info(f"Loading champion model from {model_uri}")

        try:
            pipeline = mlflow_sklearn.load_model(model_uri)
            self.logger.info("Production model loaded successfully...")
        except Exception as e:
            self.logger.warning(f"Could not load Production model. Error: {e}. Falling back to best run.")
            client = MlflowClient()
            experiment_name = self.config.get("experiment_name", "Fraud_Detection_Training")
            experiment = client.get_experiment_by_name(experiment_name)
            if experiment is None:
                raise ValueError(f"MLflow experiment not found: {experiment_name}") from e
            runs = client.search_runs(experiment_ids=[experiment.experiment_id], order_by=["metrics.test_pr_auc DESC"], max_results=1)
            if not runs:
                raise ValueError("No models found in MLflow.") from e
            model_uri = f"runs:/{runs[0].info.run_id}/model"
            self.logger.info(f"Fallback to Run ID: {runs[0].info.run_id}")
            pipeline = mlflow_sklearn.load_model(model_uri)

        # 3. Extract the underlying tree model for SHAP
        if pipeline is None:
            raise ValueError(f"Model is not loaded: {model_uri}")

        model = pipeline.named_steps["model"]

        # Transform data if there is a preprocessor step (e.g. Random Forest OrdinalEncoder)
        if "preprocessor" in pipeline.named_steps:
            self.logger.info("Applying preprocessing before SHAP...")
            X_sample_transformed = pipeline.named_steps["preprocessor"].transform(X_sample)
            X_shap = pd.DataFrame(X_sample_transformed, columns=X_sample.columns)
        else:
            X_shap = X_sample

        # 4. Generate Explanations using SHAPEngine
        from explainability.shap_engine import SHAPEngine

        engine = SHAPEngine()
        explanations = engine.explain(model=model, X_sample=X_sample, X_shap=X_shap, tx_ids=list(tx_ids))

        # Save to disk as an artifact
        explain_dir = "dataset/processed"
        os.makedirs(explain_dir, exist_ok=True)
        out_path = os.path.join(explain_dir, "explanations.json")
        with open(out_path, "w") as f:
            json.dump(explanations, f, indent=4)

        self.logger.info(f"Generated explanations saved to {out_path}")

        return {
            "metadata": {
                "transactions_explained": len(X_shap),
                "model_uri": model_uri,
            },
            "artifacts": {"explanations_file": out_path},
        }
