import os
from typing import Any

import joblib
import mlflow
import mlflow.sklearn as mlflow_sklearn
import pandas as pd

from ml.training.trainer import ModelTrainer
from pipelines.base_pipeline import BasePipeline
from shared import configure_logging, constants

configure_logging(log_file="training.log")


class TrainingPipeline(BasePipeline):
    """
    Orchestrates the model training process.
    Responsible for:
      - Loading train and validation datasets
      - Initializing MLflow experiment tracking
      - Executing ModelTrainer
      - Saving local model artifact
      - Logging model and parameters to MLflow
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.target_col = constants.TARGET_FEATURE
        self.experiment_name = self.config.get("experiment_name", "Fraud_Detection_Training")

        # mlflow cofiguration
        mlflow_uri = self.config.get("mlflow_tracking_uri", "")
        if mlflow_uri:
            mlflow.set_tracking_uri(mlflow_uri)
        mlflow.set_experiment(self.experiment_name)

    # Load the training data and validation data
    def _load_data(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        processed_dir = constants.PROCESSED_DATASET_DIR
        train_path = os.path.join(processed_dir, constants.TRAIN_DATA_FILE)
        val_path = os.path.join(processed_dir, constants.VAL_DATA_FILE)

        self.logger.info(f"Loading training data from {train_path}")
        train_df = pd.read_parquet(train_path)

        self.logger.info(f"Loading validation data from {val_path}")
        val_df = pd.read_parquet(val_path)

        return train_df, val_df

    def _execute(self) -> dict[str, Any]:
        # 1. Load Data
        train_df, val_df = self._load_data()

        # 2. Separate Features and Target, removing UIDs which are not features
        # We must drop uids to prevent the model from memorizing specific customers/devices
        drop_cols = [
            self.target_col,
            "TransactionID",
            "uid_card",
            "uid_card_email",
            "uid_card_device",
            "TransactionDT",  # Dropping raw timestamp as we extracted temporal features
        ]

        # Only drop columns that actually exist in the dataframe
        train_drop = [c for c in drop_cols if c in train_df.columns]
        val_drop = [c for c in drop_cols if c in val_df.columns]

        X_train = train_df.drop(columns=train_drop)
        y_train = train_df[self.target_col]

        X_val = val_df.drop(columns=val_drop)
        y_val = val_df[self.target_col]

        # 3. Setup Trainer
        model_config = self.config.get("model", {"model_type": "xgboost", "model_params": {}})
        trainer = ModelTrainer(config=model_config)

        # 4. MLflow Tracking Context
        tuning_state = self.config.get("tuning_state", "default")
        run_name = f"{trainer.model_type}_{tuning_state}"
        self.logger.info(f"Starting MLflow run: {run_name}")

        with mlflow.start_run(run_name=run_name):
            # Log basic parameters
            mlflow.log_params(model_config.get("model_params", {}))
            mlflow.log_param("model_type", trainer.model_type)
            mlflow.log_param("train_rows", len(X_train))
            mlflow.log_param("val_rows", len(X_val))
            mlflow.log_param("num_features", len(X_train.columns))
            mlflow.log_param("trained_features", X_train.columns.tolist())

            # 5. Execute Training
            pipeline = trainer.train(X_train, y_train, X_val, y_val)

            # 6. Save Model Locally
            models_dir = getattr(constants, "MODELS_DIR", "models")
            os.makedirs(models_dir, exist_ok=True)
            local_model_path = os.path.join(models_dir, trainer.model_type + ".pkl")

            self.logger.info(f"Saving model locally to {local_model_path}")
            joblib.dump(pipeline, local_model_path)

            # 7. Log Model to MLflow
            # We log the entire scikit-learn Pipeline so preprocessing (if any) is preserved
            # skops requires whitelisting non-sklearn types to save them securely
            trusted_types = [
                "xgboost.core.Booster",
                "xgboost.sklearn.XGBClassifier",
                "lightgbm.basic.Booster",
                "lightgbm.sklearn.LGBMClassifier",
                "collections.OrderedDict",
            ]
            mlflow_sklearn.log_model(pipeline, name="model", skops_trusted_types=trusted_types)

            active_run = mlflow.active_run()
            run_id = active_run.info.run_id if active_run else "unknown"
            self.logger.info(f"Model logged to MLflow with Run ID: {run_id}")

        # 8. Return metrics to BasePipeline
        return {
            "metadata": {
                "model_type": trainer.model_type,
                "mlflow_run_id": run_id,
                "local_model_path": local_model_path,
                "train_rows": len(X_train),
                "val_rows": len(X_val),
                "features_used": len(X_train.columns),
            }
        }
