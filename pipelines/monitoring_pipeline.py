import os
from typing import Any

import pandas as pd
import yaml
from evidently import DataDefinition, Dataset, Report
from evidently.presets import DataDriftPreset

from pipelines.base_pipeline import BasePipeline


class MonitoringPipeline(BasePipeline):
    """
    Production Data Drift & Distribution Monitoring Pipeline using Evidently AI.

    Compares live/current scoring data against reference training distributions
    to detect covariate shift and trigger automated retraining signals.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.config_path = self.config.get("config_path", "configs/monitoring.yaml")
        self.monitoring_config = self._load_config()

    def _load_config(self) -> dict[str, Any]:
        if os.path.exists(self.config_path):
            with open(self.config_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    def _execute(self) -> dict[str, Any]:
        # 1. Resolve paths
        data_cfg = self.monitoring_config.get("data", {})
        drift_cfg = self.monitoring_config.get("drift", {})
        reports_cfg = self.monitoring_config.get("reports", {})

        ref_path = self.config.get("reference_path", data_cfg.get("reference_path", "dataset/processed/train.parquet"))
        cur_path = self.config.get("current_path", data_cfg.get("current_path", "dataset/processed/test.parquet"))
        output_dir = reports_cfg.get("output_dir", "monitoring/reports")
        html_name = reports_cfg.get("html_report_name", "data_drift_report.html")
        json_name = reports_cfg.get("json_report_name", "data_drift_report.json")
        drift_threshold = float(drift_cfg.get("drift_share_threshold", 0.30))

        if not os.path.exists(ref_path):
            raise FileNotFoundError(f"Reference data not found at '{ref_path}'")
        if not os.path.exists(cur_path):
            raise FileNotFoundError(f"Current data not found at '{cur_path}'")

        # 2. Load Reference & Current Data
        self.logger.info(f"Loading reference data from {ref_path}...")
        ref_df = pd.read_parquet(ref_path) if ref_path.endswith(".parquet") else pd.read_csv(ref_path)

        self.logger.info(f"Loading current data from {cur_path}...")
        cur_df = pd.read_parquet(cur_path) if cur_path.endswith(".parquet") else pd.read_csv(cur_path)

        # Drop non-feature metadata if present
        cols_to_exclude = ["TransactionID", "isFraud", "uid_card", "uid_card_email", "uid_card_device"]
        features_to_monitor = [c for c in ref_df.columns if c in cur_df.columns and c not in cols_to_exclude]

        ref_sample = ref_df[features_to_monitor].copy()
        cur_sample = cur_df[features_to_monitor].copy()

        # Sample if dataset is very large for low-latency report generation
        if len(ref_sample) > 10000:
            ref_sample = ref_sample.sample(n=10000, random_state=42)
        if len(cur_sample) > 10000:
            cur_sample = cur_sample.sample(n=10000, random_state=42)

        # 3. Classify Numerical vs Categorical Columns
        categorical_cols = [c for c in features_to_monitor if ref_sample[c].dtype == "object" or ref_sample[c].dtype.name == "category"]
        numerical_cols = [c for c in features_to_monitor if c not in categorical_cols]

        self.logger.info(f"Monitoring {len(numerical_cols)} numerical and {len(categorical_cols)} categorical features.")

        data_definition = DataDefinition(
            numerical_columns=numerical_cols,
            categorical_columns=categorical_cols,
        )

        # 4. Build Evidently Dataset wrappers
        ref_dataset = Dataset.from_pandas(ref_sample, data_definition=data_definition)
        cur_dataset = Dataset.from_pandas(cur_sample, data_definition=data_definition)

        # 5. Run Data Drift Report
        self.logger.info("Executing Evidently DataDriftPreset analysis...")
        report = Report(metrics=[DataDriftPreset()])
        eval_result = report.run(reference_data=ref_dataset, current_data=cur_dataset)
        report_dict = eval_result.dict()

        # 6. Save Reports
        os.makedirs(output_dir, exist_ok=True)
        html_path = os.path.join(output_dir, html_name)
        json_path = os.path.join(output_dir, json_name)

        eval_result.save_html(html_path)
        eval_result.save_json(json_path)
        self.logger.info(f"HTML report saved to {html_path}")
        self.logger.info(f"JSON report saved to {json_path}")

        # 7. Extract Summary Telemetry
        drift_metric = next(
            (m for m in report_dict.get("metrics", []) if m.get("config", {}).get("type") == "evidently:metric_v2:DriftedColumnsCount"),
            None,
        )

        if drift_metric:
            drift_values = drift_metric.get("value", {})
            total_cols = int(drift_values.get("total", len(features_to_monitor)))
            drifted_cols = int(drift_values.get("count", 0))
            drift_share = float(drift_values.get("share", 0.0))
        else:
            total_cols = len(features_to_monitor)
            drifted_cols = 0
            drift_share = 0.0

        dataset_drift = drift_share > drift_threshold

        self.logger.info(f"Drift Summary: {drifted_cols}/{total_cols} columns drifted ({drift_share:.1%}). Dataset Drift: {dataset_drift}")

        return {
            "artifacts": {
                "html_report": html_path,
                "json_report": json_path,
            },
            "metadata": {
                "total_features": total_cols,
                "drifted_features": drifted_cols,
                "drift_share": drift_share,
                "drift_threshold": drift_threshold,
                "dataset_drift_detected": dataset_drift,
                "retraining_triggered": dataset_drift,
            },
        }


if __name__ == "__main__":
    pipeline = MonitoringPipeline()
    result = pipeline.run()
    print("Monitoring Pipeline Status:", result.status)
    print("Metadata:", result.metadata)
