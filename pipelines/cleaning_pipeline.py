import logging
import os

import pandas as pd

from database.connection import Database
from shared import configure_logging, constants

configure_logging(log_file="cleaning.log")


class CleaningPipeline:
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

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.database = Database()
        self.report_dir = "dataset/cleaning_report"
        os.makedirs(self.report_dir, exist_ok=True)
        self.report_path = os.path.join(self.report_dir, "cleaning_report.json")
        self.trans_table_name = constants.TRANSACTION_TABLE
        self.iden_table_name = constants.IDENTITY_TABLE
        self.report_data = {}

    def run(self) -> bool:
        self.logger.info("=" * 60)
        self.logger.info("Starting Data Cleaning Pipeline")
        self.logger.info("=" * 60)

        try:

            self._validate_database_connection()
            trans_df = self._load_transaction_data()
            iden_df = self._load_identity_data()

            # Merge the dataframes
            self.logger.info("Merging transaction and identity data...")
            trans_len = len(trans_df)
            df = trans_df.merge(iden_df, how="left", on="TransactionID")

            # Free up memory immediately after merge
            del trans_df
            del iden_df
            import gc

            gc.collect()

            # Verifying that merge has not increased the row count
            if len(df) != trans_len:
                raise ValueError(
                    "Merge increased transaction row count. "
                    "TransactionID may not be unique in identity_raw."
                )

            df = self._drop_columns(df)

            is_valid = True
            return is_valid
        except Exception as e:
            self.logger.exception(f"Cleaning Pipeline failed: {e}")
            raise e

    # Validating the connection
    def _validate_database_connection(self) -> None:
        self.logger.info("Testing Database connection")
        if not self.database.test_connection():
            raise ConnectionError(
                "Could not connect to PostgreSQL. "
                "Check DATABASE_URL or ensure PostgreSQL is running."
            )
        self.logger.info("Database connection successful.")

    # Loading Transaction Dataset
    def _load_transaction_data(self) -> pd.DataFrame:
        self.logger.info("Loading Transaction dataset from table: %s", self.trans_table_name)
        query = f"SELECT * FROM {self.trans_table_name}"
        df = pd.read_sql(query, self.database.get_engine())
        self.logger.info(
            f"Transaction data is loaded: {len(df)} rows, {len(df.columns.to_list())} columns"
        )
        return df

    # Loading Identity Dataset
    def _load_identity_data(self) -> pd.DataFrame:
        self.logger.info("Loading identity dataset from table: %s", self.iden_table_name)
        query = f"SELECT * FROM {self.iden_table_name}"
        df = pd.read_sql(query, self.database.get_engine())
        self.logger.info(
            f"identity data is loaded: {len(df)} rows, {len(df.columns.to_list())} columns"
        )
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
            self.logger.info(
                "No unwanted columns found (all loaded columns match selection requirements)."
            )

        return df

    # def _filling_missing_values(self) -> pd.DataFrame:
    #     self.logger.info("-"*30)
    #     self.logger.info("Filling Missing values")

    #     try:

    #     except Exception as e:
    #        raise e
