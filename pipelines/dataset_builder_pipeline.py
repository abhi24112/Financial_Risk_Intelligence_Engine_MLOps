import json
import logging
import os

import numpy as np
import pandas as pd

from shared import configure_logging, constants

configure_logging(log_file="data_builder.log")


class DatasetBuilderPipeline:

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.report_dir = "dataset/dataset_builder_pipeline_report"
        os.makedirs(self.report_dir, exist_ok=True)
        self.report_path = os.path.join(self.report_dir, "dataset_builder_pipeline_report.json")
        self.report_data = {}

    def run(self):
        self.logger.info("Starting Dataset Builder Pipeline")
        try:
            df = self._load_processed_parquet()

            # 1. Convert string/object columns to category (Optimized for XGBoost/LightGBM)
            cat_cols = df.select_dtypes(include=["object", "string"]).columns
            if len(cat_cols) > 0:
                df[cat_cols] = df[cat_cols].astype("category")
                self.logger.info(
                    f"Converted {len(cat_cols)} categorical columns to 'category' dtype."
                )

            # 2. Group-Aware Stratified Split (Train: ~71%, Val: ~14%, Test: ~14%)
            if "uid_card" not in df.columns:
                raise ValueError("uid_card feature missing. Cannot perform group-aware split.")

            self.logger.info("Performing Stratified Group-Aware split (K=7) using 'uid_card'")

            # Using K=7 gives exactly 1/7 (~14.2%) per fold.
            # We assign 1 fold to Test, 1 fold to Val, and 5 folds to Train (~71.4%)
            from sklearn.model_selection import StratifiedGroupKFold

            sgkf = StratifiedGroupKFold(n_splits=7, shuffle=True, random_state=42)
            folds = list(sgkf.split(df, y=df[constants.TARGET_FEATURE], groups=df["uid_card"]))

            # Extract indices for the first two folds
            test_idx = folds[0][1]
            val_idx = folds[1][1]

            # Train indices are everything else
            train_idx = np.setdiff1d(np.arange(len(df)), np.concatenate([test_idx, val_idx]))

            train_df = df.iloc[train_idx].copy()
            val_df = df.iloc[val_idx].copy()
            test_df = df.iloc[test_idx].copy()

            # 3. Save the splits
            self._save_dataset(train_df, "train.parquet")
            self._save_dataset(val_df, "val.parquet")
            self._save_dataset(test_df, "test.parquet")

            # 4. Generate report
            self.report_data = {
                "status": "success",
                "total_rows": len(df),
                "total_features": len(df.columns),
                "train_shape": train_df.shape,
                "val_shape": val_df.shape,
                "test_shape": test_df.shape,
                "unique_groups_train": train_df["uid_card"].nunique(),
                "unique_groups_val": val_df["uid_card"].nunique(),
                "unique_groups_test": test_df["uid_card"].nunique(),
            }
            self._generate_report()

            return True
        except Exception as e:
            self.logger.exception(f"Dataset Builder Pipeline failed: {e}")
            self.report_data = {"status": "error", "error_message": str(e)}
            self._generate_report()
            raise e

    # Loading cleaned parquet file
    def _load_processed_parquet(self) -> pd.DataFrame:
        path = os.path.join(
            getattr(constants, "PROCESSED_DATASET_DIR", os.path.join("dataset", "processed")),
            "features.parquet",
        )
        self.logger.info(f"Loading engineered features from {path}")
        df = pd.read_parquet(path=path)
        if df.empty:
            raise ImportError("DataFrame is empty. Failed to load processed data.")
        return df

    # Generating report
    def _generate_report(self) -> None:
        self.logger.info(f"Generating pipeline report at {self.report_path}...")
        with open(self.report_path, "w") as f:
            json.dump(self.report_data, f, indent=4)
        self.logger.info("Report generated successfully.")

    # Saving the parquet files
    def _save_dataset(self, df: pd.DataFrame, filename: str) -> None:
        processed_dir = getattr(
            constants, "PROCESSED_DATASET_DIR", os.path.join("dataset", "processed")
        )
        os.makedirs(processed_dir, exist_ok=True)
        path = os.path.join(processed_dir, filename)
        self.logger.info(f"Saving {filename} ({df.shape[0]} rows) to {path}...")
        df.to_parquet(path, index=False)
