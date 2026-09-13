import logging
from typing import Any

import pandas as pd
import shap


class SHAPEngine:
    """
    Core engine for computing SHAP values and mapping them to
    human-readable, analyst-facing strings.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def _get_human_readable_reason(self, feature_name: str, shap_value: float, feature_value: Any) -> str:
        """Translates raw SHAP features into analyst-readable strings."""
        direction = "increased" if shap_value > 0 else "decreased"

        # Round numeric values for cleaner display
        if isinstance(feature_value, float):
            feature_value = round(feature_value, 2)

        is_missing = feature_value == -1.0 or feature_value == -1 or pd.isna(feature_value)

        if feature_name == "TransactionAmt":
            return f"Transaction amount (${feature_value}) {direction} the risk score."
        elif feature_name.startswith("card"):
            return f"Customer card attribute '{feature_name}' (Value: {feature_value}) {direction} the risk score."
        elif feature_name.startswith("C") and feature_name[1:].isdigit():
            if is_missing:
                return f"Unobserved transaction velocity counter '{feature_name}' (missing history) {direction} the risk score."
            return f"Transaction frequency counter '{feature_name}' (Count: {feature_value}) {direction} the risk score."
        elif feature_name.startswith("D") and feature_name[1:].isdigit():
            if is_missing:
                return f"Unobserved transaction interval '{feature_name}' {direction} the risk score."
            return f"Timedelta interval '{feature_name}' ({feature_value} units) {direction} the risk score."
        elif feature_name in ["id_15", "id_16"]:
            return f"Device identity verification flag '{feature_name}' {direction} the risk score."
        elif feature_name.startswith("id_"):
            return f"Identity/Device attribute '{feature_name}' {direction} the risk score."
        elif feature_name == "ProductCD":
            return f"Product transaction category '{feature_name}' {direction} the risk score."
        elif feature_name in ["addr1", "addr2"]:
            if is_missing:
                return f"Missing regional/billing address code '{feature_name}' {direction} the risk score."
            return f"Regional address attribute '{feature_name}' (Value: {feature_value}) {direction} the risk score."
        elif feature_name in ["P_emaildomain", "R_emaildomain"]:
            return f"Email domain profile '{feature_name}' {direction} the risk score."
        elif feature_name == "DeviceType":
            return f"Device type '{feature_value}' {direction} the risk score."
        elif feature_name == "is_new_device":
            return f"First-time device usage flag {direction} the risk score."
        elif feature_name == "is_new_email":
            return f"First-time email usage flag {direction} the risk score."
        elif feature_name == "time_since_last_transaction":
            if is_missing:
                return f"No previous transaction record found for this card {direction} the risk score."
            return f"Time elapsed since previous transaction ({feature_value}s) {direction} the risk score."
        elif "missing" in feature_name.lower():
            return f"Missing information indicator in '{feature_name}' {direction} the risk score."
        else:
            return f"Behavioral metric '{feature_name}' (Value: {feature_value}) {direction} the risk score."

    def explain(self, model: Any, X_sample: pd.DataFrame, X_shap: pd.DataFrame, tx_ids: list[Any], top_k: int = 3) -> dict[str, Any]:
        """
        Calculates SHAP values for a batch of transactions and generates explanations.

        Args:
            model: The underlying tree-based model (e.g., XGBoost, LightGBM)
            X_sample: Original feature dataframe (used for human-readable values)
            X_shap: Preprocessed feature dataframe (used for SHAP computation)
            tx_ids: List of transaction IDs corresponding to the rows
            top_k: Number of top reasons to return per transaction

        Returns:
            A dictionary mapping transaction IDs to their explanations.
        """
        self.logger.info("Initializing SHAP TreeExplainer...")
        explainer = shap.TreeExplainer(model)

        self.logger.info(f"Calculating SHAP values for {len(X_shap)} transactions...")
        X_input = X_shap.values if isinstance(X_shap, pd.DataFrame) else X_shap
        shap_values = explainer.shap_values(X_input)

        # LightGBM/XGBoost binary objective format handling
        if isinstance(shap_values, list):
            shap_values = shap_values[1]

        explanations = {}

        for i in range(len(X_shap)):
            tx_id = str(tx_ids[i])
            tx_shap_vals = shap_values[i]

            # Combine feature names, their SHAP values, and the actual feature value from X_sample
            feature_impacts = list(zip(X_shap.columns, tx_shap_vals, X_sample.iloc[i].values, strict=False))

            # Sort by absolute SHAP value (importance)
            feature_impacts.sort(key=lambda x: abs(x[1]), reverse=True)

            # Take top K most important features for this specific transaction
            top_features = feature_impacts[:top_k]

            reasons = [self._get_human_readable_reason(feat, float(shap_val), feat_val) for feat, shap_val, feat_val in top_features]

            explanations[tx_id] = {
                "top_features": [f[0] for f in top_features],
                "shap_values": [float(f[1]) for f in top_features],
                "reasons": reasons,
            }

        return explanations
