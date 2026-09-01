import os
from typing import Any

import numpy as np
import pandas as pd

from pipelines.base_pipeline import BasePipeline
from shared import configure_logging, constants

configure_logging(log_file="feature_engineering.log")


class FeatureEngineeringPipeline(BasePipeline):
    """
    Pipeline to do feature engineering by adding feature and
    adding missiness significance features.

    Responsibilities:
        - Pipeline responsible for filling missing values and creating "feature_missing" columns.
        - Creating address_missing for "addr1" and "addr2"
        - Adding new feature to the data.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)

    def _execute(self) -> dict[str, Any]:
        df = self._load_cleaned_parquet()
        original_cols = set(df.columns)

        self.logger.info("Sorting by TransactionDT to prevent temporal leakage...")
        df = df.sort_values("TransactionDT").reset_index(drop=True)

        df = self._handle_missing_values(df)
        df = self._add_temporal_features(df)
        df = self._add_amount_features(df)
        df = self._create_uids(df)
        df = self._add_behavioral_stats(df)
        df = self._add_velocity_and_time_features(df)
        df = self._add_novelty_features(df)

        self._save_features(df)

        new_cols = list(set(df.columns) - original_cols)

        return {
            "metadata": {
                "total_rows": len(df),
                "total_features": len(df.columns),
                "new_features_created": len(new_cols),
                "new_features_list": new_cols,
            }
        }

    # Loading cleaned parquet file
    def _load_cleaned_parquet(self) -> pd.DataFrame:
        path = os.path.join(constants.INTERIM_DATASET_DIR, constants.CLEANED_DATA_FILE)
        self.logger.info(f"Loading cleaned data from {path}")
        df = pd.read_parquet(path=path)
        if df.empty:
            raise ImportError("DataFrame is empty. Failed to load cleaned data.")
        return df

    # Imputing median in  NaN values and creating feature_missing feaures
    def _handle_missing_values(self, df: pd.DataFrame) -> pd.DataFrame:
        self.logger.info("Handling missing values (Tree-optimized strategy)...")

        # 1. Create missing indicators ONLY for addr1 and addr2 (high IV)
        # Both addr1 and add2 have same missing values,
        # Hence created only 1 missing indictor address_missing
        # 1 = Missing, 0 = Not Missing
        if "addr2" in df.columns:
            df["address_missing"] = df["addr2"].isna().astype("int32")
            self.logger.info("Created address_missing flag.")
            df = df.drop(columns=["addr1", "addr2"], errors="ignore")

        # 2. Fill missing values for object/categorical columns with 'missing'
        cat_cols = df.select_dtypes(include=["object", "category", "string"]).columns
        if len(cat_cols) > 0:
            df[cat_cols] = df[cat_cols].fillna("missing").astype(str)
            self.logger.info(f"Filled NaNs with 'missing' and casted {len(cat_cols)} categorical columns to str.")

        # 3. DO NOT impute numerical columns - XGBoost handles NaNs natively
        self.logger.info("Retained native NaNs for remaining numerical columns.")

        return df

    def _add_temporal_features(self, df: pd.DataFrame) -> pd.DataFrame:
        self.logger.info("Extracting temporal features from TransactionDT...")
        if "TransactionDT" in df.columns:
            df["transaction_hour"] = (df["TransactionDT"] // 3600) % 24
            df["transaction_dayofweek"] = (df["TransactionDT"] // (3600 * 24)) % 7
            df["is_weekend"] = (df["transaction_dayofweek"] >= 5).astype("int32")
        return df

    def _add_amount_features(self, df: pd.DataFrame) -> pd.DataFrame:
        self.logger.info("Creating transaction amount features...")
        if "TransactionAmt" in df.columns:
            df["amount_log"] = np.log1p(df["TransactionAmt"])
            df["amount_is_round"] = (df["TransactionAmt"] % 1 == 0).astype("int32")
        return df

    def _create_uids(self, df: pd.DataFrame) -> pd.DataFrame:
        self.logger.info("Constructing behavioral UIDs (card, email, device)...")
        card1_str = df["card1"].fillna(-1).astype(str)
        card2_str = df["card2"].fillna(-1).astype(str)
        df["uid_card"] = card1_str + "_" + card2_str

        if "P_emaildomain" in df.columns:
            df["uid_card_email"] = df["uid_card"] + "_" + df["P_emaildomain"].astype(str)

        if "DeviceInfo" in df.columns:
            df["uid_card_device"] = df["uid_card"] + "_" + df["DeviceInfo"].astype(str)

        return df

    def _add_behavioral_stats(self, df: pd.DataFrame) -> pd.DataFrame:
        self.logger.info("Calculating cumulative behavioral stats (past-only)...")
        grouped = df.groupby("uid_card")["TransactionAmt"]

        df["identity_transaction_count"] = grouped.cumcount() + 1
        df["identity_avg_amount"] = grouped.expanding().mean().reset_index(level=0, drop=True)
        df["amount_vs_identity_avg"] = df["TransactionAmt"] / (df["identity_avg_amount"] + 1e-5)

        return df

    def _add_velocity_and_time_features(self, df: pd.DataFrame) -> pd.DataFrame:
        self.logger.info("Calculating time-since-last and velocity features...")

        df["time_since_last_transaction"] = df.groupby("uid_card")["TransactionDT"].diff().fillna(-1)

        self.logger.info("Computing 24h rolling aggregations...")
        temp = df[["uid_card", "TransactionAmt", "TransactionDT"]].copy()
        temp["pseudo_dt"] = pd.to_datetime(temp["TransactionDT"], unit="s")

        rolling = temp.groupby("uid_card").rolling("24h", on="pseudo_dt")
        transactions_last_24h = rolling["TransactionAmt"].count().reset_index(level=0, drop=True).sort_index()
        amount_last_24h = rolling["TransactionAmt"].sum().reset_index(level=0, drop=True).sort_index()

        df["transactions_last_24h"] = transactions_last_24h.to_numpy()
        df["amount_last_24h"] = amount_last_24h.to_numpy()

        return df

    def _add_novelty_features(self, df: pd.DataFrame) -> pd.DataFrame:
        self.logger.info("Calculating novelty (is_new) features...")

        if "uid_card_email" in df.columns:
            df["is_new_email"] = (df.groupby("uid_card_email").cumcount() == 0).astype("int32")

        if "uid_card_device" in df.columns:
            df["is_new_device"] = (df.groupby("uid_card_device").cumcount() == 0).astype("int32")

        return df

    def _save_features(self, df: pd.DataFrame) -> None:
        processed_dir = getattr(constants, "PROCESSED_DATASET_DIR", os.path.join("dataset", "processed"))
        os.makedirs(processed_dir, exist_ok=True)

        output_path = os.path.join(processed_dir, "features.parquet")
        self.logger.info(f"Saving engineered features to {output_path}...")
        df.to_parquet(output_path, index=False)
        self.logger.info("Features successfully saved.")


if __name__ == "__main__":
    import sys

    pipeline = FeatureEngineeringPipeline()
    result = pipeline.run()
    if result.status != "success":
        sys.exit(1)
