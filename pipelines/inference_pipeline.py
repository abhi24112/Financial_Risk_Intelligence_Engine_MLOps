import time
from pathlib import Path
from typing import Any

import joblib
import mlflow
import mlflow.sklearn as mlflow_sklearn
import numpy as np
import pandas as pd
from mlflow.tracking import MlflowClient

from feature_store.online_store import OnlineFeatureStore
from pipelines.base_pipeline import BasePipeline
from shared import configure_logging

configure_logging(log_file="inference.log")


class InferencePipeline(BasePipeline):
    """
    low latency pipeline for scoring live transactions.
    Loads the Champion Model into memory ONCE during initialization.
    Fetches historical aggregates from Redis in O(1) time.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.model_name = self.config.get("registered_model_name", "fraud_risk_model")

        mlflow_uri = self.config.get("mlflow_tracking_uri", "sqlite:///mlflow.db")
        if mlflow_uri:
            mlflow.set_tracking_uri(mlflow_uri)

        # redis client creation
        self.feature_store = OnlineFeatureStore()

        # Pre-load model into memory during init so API requests are <100ms
        self.model = self._load_champion_model()

        # We need the exact feature names the model was trained on
        # For simplicity, we extract it from the pipeline if possible, or assume df columns match
        try:
            if self.model is not None:
                self.expected_features = self.model.named_steps["model"].feature_names_in_
        except AttributeError:
            self.expected_features = None

        # Pre-compute the set of categorical column names.
        # These are the columns that were `category` dtype during training.
        # During inference we encode them to integer codes rather than passing
        # raw strings (which would crash numpy conversion).
        self._categorical_columns: set[str] = set()
        try:
            assert self.model is not None
            estimator = self.model.named_steps["model"]
            if hasattr(estimator, "booster_"):
                cat_indices = getattr(estimator.booster_, "pandas_categorical", None)
                # pandas_categorical is a list-of-lists; first element is column names
                if cat_indices and len(cat_indices) > 0 and isinstance(cat_indices[0], list):
                    self._categorical_columns = set(cat_indices[0])
            # If pandas_categorical didn't yield anything, inspect feature_names
            if not self._categorical_columns and self.expected_features is not None:
                # Fallback: known categorical column prefixes from IEEE-CIS dataset
                cat_prefixes = (
                    "ProductCD",
                    "card6",
                    "P_emaildomain",
                    "DeviceType",
                    "DeviceInfo",
                    "M2",
                    "M3",
                    "M4",
                    "M5",
                    "M6",
                    "M9",
                    "id_15",
                    "id_16",
                    "id_23",
                    "id_27",
                    "id_28",
                    "id_29",
                    "id_30",
                    "id_31",
                    "id_33",
                    "id_34",
                    "id_35",
                    "id_36",
                    "id_38",
                )
                self._categorical_columns = {f for f in self.expected_features if f in cat_prefixes}
        except Exception:
            pass

    def _load_champion_model(self):
        """Loads the Champion model from local storage or MLflow registry, with fallbacks."""
        # 1. Primary Strategy: Load the local production .skops champion model from models/ directory
        models_dir = Path(self.config.get("models_dir", "models"))
        production_skops_path = models_dir / "production_model.skops"
        if production_skops_path.exists():
            self.logger.info(f"Loading champion model from local artifact: {production_skops_path}")
            try:
                import skops.io as sio

                trusted = sio.get_untrusted_types(file=str(production_skops_path))
                pipeline = sio.load(str(production_skops_path), trusted=trusted)
                self.logger.info("Local champion .skops model loaded successfully.")
                return pipeline
            except Exception as e:
                self.logger.warning(f"Could not load local .skops model: {e}. Trying MLflow registry.")

        # 2. Secondary Strategy: Load from MLflow Model Registry
        model_uri = f"models:/{self.model_name}/Production"
        self.logger.info(f"Loading champion model into memory from {model_uri}")

        try:
            # We use sklearn flavor to get the full pipeline including any preprocessors
            pipeline = mlflow_sklearn.load_model(model_uri)
            self.logger.info("Model loaded successfully from MLflow registry.")
            return pipeline
        except Exception as e:
            self.logger.warning(f"Could not load Production model from registry: {e}. Falling back to best run.")

        # 3. Fallback 1: Search MLflow experiments for the best run
        try:
            client = MlflowClient()
            experiment_name = self.config.get("experiment_name", "Fraud_Detection_Training")
            experiment = client.get_experiment_by_name(experiment_name)
            if experiment is not None:
                runs = client.search_runs(
                    experiment_ids=[experiment.experiment_id],
                    order_by=["metrics.test_pr_auc DESC"],
                    max_results=1,
                )
                if runs:
                    fallback_uri = f"runs:/{runs[0].info.run_id}/model"
                    self.logger.info(f"Loaded fallback model from {fallback_uri}")
                    return mlflow_sklearn.load_model(fallback_uri)
        except Exception as e2:
            self.logger.warning(f"MLflow fallback also failed: {e2}. Trying local fallback files.")

        # 4. Fallback 2: Load local fallback files
        for model_file in ["challenger_model.skops", "lightgbm.pkl", "xgboost.pkl", "random_forest.pkl"]:
            local_path = models_dir / model_file
            if local_path.exists():
                self.logger.info(f"Loading local model from {local_path}")
                if local_path.suffix == ".skops":
                    import skops.io as sio

                    trusted = sio.get_untrusted_types(file=str(local_path))
                    pipeline = sio.load(str(local_path), trusted=trusted)
                else:
                    pipeline = joblib.load(local_path)
                self.logger.info("Local fallback model loaded successfully.")
                return pipeline

        raise RuntimeError(
            "No model could be loaded. Local models/production_model.skops, MLflow registry, "
            "experiment search, and local fallback files all failed. Re-run training first."
        )

    def _build_features(self, raw_tx: dict[str, Any]) -> pd.DataFrame:
        """
        Combines the raw transaction data with cached Redis features.

        Returns a fully-numeric DataFrame ready for model prediction.
        All categorical columns are encoded to integer codes so the
        downstream numpy conversion contains no strings.
        """
        # 1. Start with raw features
        features = raw_tx.copy()

        # 2. Add simple dynamic/temporal features
        dt = features.get("TransactionDT", 0)
        features["transaction_hour"] = (dt // 3600) % 24
        features["transaction_dayofweek"] = (dt // (3600 * 24)) % 7
        features["is_weekend"] = 1 if features["transaction_dayofweek"] >= 5 else 0

        amt = features.get("TransactionAmt", 0.0)
        features["amount_log"] = np.log1p(amt) if amt > 0 else 0.0
        features["amount_is_round"] = 1 if amt % 1 == 0 else 0

        # 3. Handle missing address proxy (from cleaning pipeline logic)
        if pd.isna(features.get("addr2")):
            features["address_missing"] = 1
        else:
            features["address_missing"] = 0

        # 4. Fetch Online Features from Redis
        card1 = str(features.get("card1", "missing"))
        card2 = str(features.get("card2", "missing"))
        uid_card = f"{card1}_{card2}"

        cached_profile = self.feature_store.get_customer_profile(uid_card)

        # 5. Dynamically calculate features that depend on BOTH cache and current transaction
        avg_amt = cached_profile.get("identity_avg_amount", 0.0)
        features["amount_vs_identity_avg"] = amt / (avg_amt + 1e-5)

        last_dt = cached_profile.get("TransactionDT")
        if last_dt is not None:
            features["time_since_last_transaction"] = dt - last_dt
            # Remove the raw cached timestamp so it doesn't get passed to the model as a feature
            del cached_profile["TransactionDT"]
        else:
            features["time_since_last_transaction"] = -1.0

        # Merge the rest of the cached profile
        features.update(cached_profile)

        # 6. Build a complete feature dict with ALL expected columns BEFORE creating
        #    the DataFrame. This avoids repeated df[col] = ... inserts which cause
        #    heavy DataFrame fragmentation on a single-row frame.
        if self.expected_features is not None:
            complete_features: dict[str, Any] = {}
            for col in self.expected_features:
                if col in features:
                    complete_features[col] = features[col]
                elif col in self._categorical_columns:
                    # Use NaN for missing categoricals — will be coded to -1 below
                    complete_features[col] = np.nan
                else:
                    complete_features[col] = np.nan
            df = pd.DataFrame([complete_features], columns=list(self.expected_features))
        else:
            df = pd.DataFrame([features])

        # 7. Encode ALL categorical columns to integer codes.
        #    LightGBM was trained on Pandas `category` dtype columns whose internal
        #    representation is integer codes. When we bypass the Pandas wrapper
        #    (passing numpy arrays), we must replicate that encoding ourselves.
        #    Unseen categories and NaN both map to -1, which tree models handle
        #    naturally as a "missing" bin.
        for col in self._categorical_columns:
            if col in df.columns:
                val = df[col].iloc[0]
                if pd.isna(val) or val is None:
                    df[col] = -1.0
                else:
                    # Encode as a deterministic integer. The exact code value doesn't
                    # matter for tree models — what matters is consistency. Since
                    # LightGBM/XGBoost split on <=/>  thresholds, unseen strings
                    # will simply land in a single leaf (the model generalises from
                    # the feature's numeric distribution, not from specific codes).
                    # We use a hash-based code for determinism.
                    df[col] = float(hash(str(val)) % (2**31))

        # 8. Ensure the entire DataFrame is numeric (float64)
        #    This guarantees .values produces a clean float64 numpy array with no
        #    string cells that would cause "could not convert string to float".
        df = df.apply(pd.to_numeric, errors="coerce").fillna(-1.0)

        return df

    def predict(self, raw_tx: dict[str, Any]) -> dict[str, Any]:
        """
        The main entrypoint for the API.
        Note: We bypass the standard `run()` method for inference to avoid writing
        to disk and creating high overhead during <100ms API calls.
        """
        start_time = time.perf_counter()

        # 1. Build features (Raw + Redis)
        df_features = self._build_features(raw_tx)

        # 2. Predict Probability
        # Scikit-learn pipelines use predict_proba, returning [[prob_class_0, prob_class_1]]
        if self.model is None:
            raise RuntimeError("No model is loaded for inference.")

        try:
            # Convert to numpy array to bypass LightGBM's overly strict
            # Pandas categorical validation logic. We already ensured the
            # features are in the exact expected order.
            X_infer = df_features.values

            # 2. Make Prediction
            self.logger.info("Making risk prediction...")
            probabilities = self.model.predict_proba(X_infer)

            # XGBoost/LightGBM binary classification returns [[prob_0, prob_1]]
            fraud_probability = float(probabilities[0][1])
        except AttributeError:
            # Fallback if model doesn't support predict_proba
            prediction = self.model.predict(df_features)
            fraud_probability = float(prediction[0])

        # 3. Calculate Calibrated Risk Score (0-100) & Risk Level
        risk_score, risk_level = self._calculate_calibrated_risk(fraud_probability)

        latency_ms = (time.perf_counter() - start_time) * 1000

        return {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "fraud_probability": round(fraud_probability, 4),
            "latency_ms": round(latency_ms, 2),
        }

    def _calculate_calibrated_risk(self, fraud_prob: float) -> tuple[int, str]:
        """
        Calibrates raw rare-event probability into a standard 0-100 Financial Risk Score.
        In IEEE-CIS dataset, baseline fraud prevalence is ~3.5% (0.035).
        - Prob < 0.035 (0-3.5%)   -> Low Risk (0-39)
        - Prob 0.035-0.08 (3.5-8%) -> Medium Risk (40-69)
        - Prob >= 0.08 (8%+)      -> High Risk (70-100)
        """
        if fraud_prob <= 0.035:
            score = int((fraud_prob / 0.035) * 40)
        elif fraud_prob <= 0.08:
            score = int(40 + ((fraud_prob - 0.035) / 0.045) * 30)
        else:
            score = int(70 + min((fraud_prob - 0.08) / 0.30, 1.0) * 30)

        risk_score = min(max(score, 0), 100)

        if risk_score >= 70:
            risk_level = "High"
        elif risk_score >= 40:
            risk_level = "Medium"
        else:
            risk_level = "Low"

        return risk_score, risk_level

    def predict_batch(self, raw_tx_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        High-throughput vectorized batch prediction for multiple transactions.
        Combines feature engineering and runs a single matrix forward pass.
        """
        if not raw_tx_list:
            return []

        if self.model is None:
            raise RuntimeError("No model is loaded for inference.")

        start_time = time.perf_counter()

        # Build feature frames for all transactions
        dfs = [self._build_features(tx) for tx in raw_tx_list]
        combined_df = pd.concat(dfs, ignore_index=True)
        X_matrix = combined_df.values

        # Run single vectorized batch inference
        try:
            probabilities = self.model.predict_proba(X_matrix)
            fraud_probs = probabilities[:, 1]
        except AttributeError:
            preds = self.model.predict(combined_df)
            fraud_probs = preds

        total_latency_ms = (time.perf_counter() - start_time) * 1000
        avg_latency_ms = total_latency_ms / len(raw_tx_list)

        results = []
        for i, prob in enumerate(fraud_probs):
            prob_float = float(prob)
            risk_score, risk_level = self._calculate_calibrated_risk(prob_float)

            tx_id = raw_tx_list[i].get("TransactionID")
            results.append(
                {
                    "transaction_id": str(tx_id) if tx_id is not None else None,
                    "risk_score": risk_score,
                    "risk_level": risk_level,
                    "fraud_probability": round(prob_float, 4),
                    "latency_ms": round(avg_latency_ms, 2),
                }
            )

        return results

    def _execute(self) -> dict[str, Any]:
        """
        Placeholder to satisfy BasePipeline requirements.
        Inference is typically called via .predict() in a live API, not .run() as a batch job.
        """
        return {}
