import os
from typing import Any

import pandas as pd

from database.connection import Database
from pipelines.base_pipeline import BasePipeline
from shared import configure_logging, constants

configure_logging(log_file="cleaning.log")


class CleaningPipeline(BasePipeline):
    """
    Pipeline responsible for cleaning raw data
    and saving cleaned data as Parquet.

    Responsibilities:
        - Remove explicitly rejected features
        - Handle missing values
        - Normalize categorical values
        - Remove invalid/impossible records
        - Save cleaned data as Parquet
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.database = Database()
        self.trans_table_name = constants.TRANSACTION_TABLE
        self.iden_table_name = constants.IDENTITY_TABLE

    def _execute(self) -> dict[str, Any]:
        self._validate_database_connection()
        trans_df = self._load_transaction_data()
        iden_df = self._load_identity_data()
        df_import_status = True

        # Downcast before merge to save memory
        trans_df = self._downcast_datatypes(trans_df)
        iden_df = self._downcast_datatypes(iden_df)
        is_downcasted = True

        # Merge the dataframes
        self.logger.info("Merging transaction and identity data...")
        trans_len = len(trans_df)
        df = trans_df.merge(iden_df, how="left", on="TransactionID")
        total_rows = len(df)
        duplicates_count = int(df.duplicated().sum())

        # Free up memory immediately after merge
        del trans_df
        del iden_df
        import gc

        gc.collect()

        # Verifying that merge has not increased the row count
        if len(df) != trans_len:
            raise ValueError("Merge increased transaction row count. " "TransactionID may not be unique in identity_raw.")

        df = self._drop_columns(df)
        df = self._normalize_strings(df)
        df = self._remove_invalid_data(df)
        rowcount_after_drop = len(df)

        self._save_processed_data(df)

        # Return metadata to the BasePipeline
        return {
            "metadata": {
                "DataFrame_import_status": df_import_status,
                "total_rows": total_rows,
                "duplicates_count": duplicates_count,
                "isDowncasted": is_downcasted,
                "row_count_after_col_drop": rowcount_after_drop,
            }
        }

    # Validating the connection
    def _validate_database_connection(self) -> None:
        self.logger.info("Testing Database connection")
        if not self.database.test_connection():
            raise ConnectionError("Could not connect to PostgreSQL. " "Check DATABASE_URL or ensure PostgreSQL is running.")
        self.logger.info("Database connection successful.")

    # Loading Transaction Dataset
    def _load_transaction_data(self) -> pd.DataFrame:
        self.logger.info("Loading Transaction dataset from table: %s", self.trans_table_name)
        query = f"SELECT * FROM {self.trans_table_name}"
        df = pd.read_sql(query, self.database.get_engine())
        self.logger.info(f"Transaction data is loaded: {len(df)} rows, {len(df.columns.to_list())} columns")
        return df

    # Loading Identity Dataset
    def _load_identity_data(self) -> pd.DataFrame:
        self.logger.info("Loading identity dataset from table: %s", self.iden_table_name)
        query = f"SELECT * FROM {self.iden_table_name}"
        df = pd.read_sql(query, self.database.get_engine())
        self.logger.info(f"identity data is loaded: {len(df)} rows, {len(df.columns.to_list())} columns")
        return df

    # Dropping unwanted columns
    def _drop_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        self.logger.info("Dropping unwanted columns...")

        col_drop = []

        for column in df.columns:
            if column not in constants.SELECTED_FEATURES_TO_KEEP:
                col_drop.append(column)

        if col_drop:
            df = df.drop(columns=col_drop)

            self.logger.info(f"Dropped {len(col_drop)} columns: {col_drop}")
        else:
            self.logger.info("No unwanted columns found (all loaded columns match selection requirements).")

        return df

    # Down casting for saving memory
    def _downcast_datatypes(self, df: pd.DataFrame) -> pd.DataFrame:
        self.logger.info("Downcasting data types to save memory...")
        float_cols = df.select_dtypes(include=["float64"]).columns
        int_cols = df.select_dtypes(include=["int64"]).columns

        df[float_cols] = df[float_cols].astype("float32")
        df[int_cols] = df[int_cols].astype("int32")
        self.logger.info(f"Downcasted {len(float_cols)} float64 and {len(int_cols)} int64 columns.")
        return df

    # removing leading and trailing spaces.
    def _normalize_strings(self, df: pd.DataFrame) -> pd.DataFrame:
        self.logger.info("Normalizing string columns...")
        for col in df.columns:
            if df[col].dtype == "object":
                df[col] = df[col].str.strip().str.lower()
        return df

    # removing invalid TransactionAmt
    def _remove_invalid_data(self, df: pd.DataFrame) -> pd.DataFrame:
        self.logger.info("Filtering out invalid records...")
        if "TransactionAmt" in df.columns:
            invalid_amt_mask = df["TransactionAmt"] <= 0
            invalid_count = invalid_amt_mask.sum()
            if invalid_count > 0:
                self.logger.info(f"Removing {invalid_count} records with TransactionAmt <= 0")
                df = df[~invalid_amt_mask]
        return df

    # Saving cleaned datain .parquet file
    def _save_processed_data(self, df: pd.DataFrame) -> None:
        processed_dir = constants.INTERIM_DATASET_DIR
        os.makedirs(processed_dir, exist_ok=True)

        output_path = os.path.join(processed_dir, "cleaned.parquet")
        self.logger.info(f"Saving cleaned dataset to {output_path}...")
        df.to_parquet(output_path, index=False)
        self.logger.info("Dataset successfully saved.")


if __name__ == "__main__":
    import sys

    pipeline = CleaningPipeline()
    result = pipeline.run()
    if result.status != "success":
        sys.exit(1)
