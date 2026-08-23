import logging
from typing import Any

# Models
import lightgbm as lgb
import pandas as pd
import xgboost as xgb
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier

# Pipeline and encoder
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder


class ModelTrainer:
    """
    Core ML logic for training fraud detection models.
    Supports toggling between different architectures via configuration.
    Handles algorithm-specific needs (e.g., encoding for Random Forest,
    native categories for Trees).
    """

    def __init__(self, config: dict[str, Any]):
        self.logger = logging.getLogger(__name__)
        # Default to xgboost if not specified
        self.model_type = config.get("model_type", "xgboost").lower()
        self.params = config.get("model_params", {})

    # Identify which columns are categorical.
    def _get_categorical_columns(self, X: pd.DataFrame) -> list:
        return list(X.select_dtypes(include=["category", "object", "string"]).columns)

    def _build_pipeline(self, X_train: pd.DataFrame, y_train: pd.Series) -> Pipeline:
        """
        Constructs a Scikit-Learn Pipeline containing preprocessing (if any) and the model.
        """
        cat_cols = self._get_categorical_columns(X_train)

        # 1. Calculate class weights for highly imbalanced data (Fraud is rare)
        num_neg = (y_train == 0).sum()
        num_pos = (y_train == 1).sum()
        scale_pos_weight = num_neg / num_pos if num_pos > 0 else 1.0

        self.logger.info(f"Class imbalance calculated. scale_pos_weight: {scale_pos_weight:.2f}")

        # 2. Build model architecture based on selection
        if self.model_type == "xgboost":
            default_params = {
                "objective": "binary:logistic",
                "eval_metric": "auc",
                "scale_pos_weight": scale_pos_weight,
                "enable_categorical": True,
                "tree_method": "hist",  # Required for XGBoost native categorical support
                "random_state": 42,
            }
            default_params.update(self.params)

            # model
            model = xgb.XGBClassifier(**default_params)

            # No preprocessing needed, XGBoost handles categories natively
            return Pipeline(steps=[("model", model)])

        elif self.model_type == "lightgbm":
            default_params = {
                "objective": "binary",
                "metric": "auc",
                "scale_pos_weight": scale_pos_weight,
                "random_state": 42,
                "verbose": -1,
            }
            default_params.update(self.params)
            model = lgb.LGBMClassifier(**default_params)

            # No preprocessing needed, LightGBM handles categories natively
            return Pipeline(steps=[("model", model)])

        elif self.model_type == "random_forest":
            default_params = {
                "n_estimators": 100,
                "class_weight": "balanced",
                "random_state": 42,
                "n_jobs": -1,
            }
            default_params.update(self.params)
            model = RandomForestClassifier(**default_params)

            # Random Forest REQUIRES ordinal encoding for categories
            if len(cat_cols) > 0:
                self.logger.info(
                    f"Adding OrdinalEncoder for {len(cat_cols)} categorical "
                    "columns for Random Forest."
                )
                # handle_unknown='use_encoded_value' ensures unseen test
                # categories don't crash the pipeline
                encoder = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
                preprocessor = ColumnTransformer(
                    transformers=[("cat", encoder, cat_cols)], remainder="passthrough"
                )
                return Pipeline(steps=[("preprocessor", preprocessor), ("model", model)])
            else:
                return Pipeline(steps=[("model", model)])
        else:
            raise ValueError(
                f"Unsupported model_type: {self.model_type}. Choose from: "
                "xgboost, lightgbm, random_forest"
            )

    def train(
        self, X_train: pd.DataFrame, y_train: pd.Series, X_val: pd.DataFrame, y_val: pd.Series
    ) -> Pipeline:
        """
        Executes model training with optional evaluation monitoring.
        """
        self.logger.info(f"Initializing {self.model_type} pipeline...")
        pipeline = self._build_pipeline(X_train, y_train)

        self.logger.info(f"Starting training on {len(X_train)} rows...")

        if self.model_type in ["xgboost", "lightgbm"]:
            # Extract underlying model to pass the validation set for monitoring
            model = pipeline.named_steps["model"]

            fit_params: dict[str, Any] = {"eval_set": [(X_val, y_val)]}
            if self.model_type == "xgboost":
                fit_params["verbose"] = False
            elif self.model_type == "lightgbm":
                pass

            model.fit(X_train, y_train, **fit_params)
        else:
            # Random Forest and Standard Scikit-Learn models are fit directly
            pipeline.fit(X_train, y_train)

        self.logger.info(f"{self.model_type} training completed successfully.")
        return pipeline
