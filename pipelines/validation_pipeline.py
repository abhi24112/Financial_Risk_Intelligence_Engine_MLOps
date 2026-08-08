import json
import logging
import os

import pandas as pd

from database.connection import Database
from shared import configure_logging, constants

configure_logging(log_file="validation.log")


class ValidationPipeline:
    """
    Pipeline responsible for validating raw datasets
    in the PostgreSQL database.

    Responsibilities:
        - Check for missing primary keys
        - Check for duplicate primary keys
        - Validate essential columns
        - Generate validation report
        - Stop the DAG on failure (returns False)
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.database = Database()
        self.report_dir = "dataset/validation_reports"
        os.makedirs(self.report_dir, exist_ok=True)
        self.report_path = os.path.join(self.report_dir, "validation_report.json")
        self.report_data = {}

    def run(self) -> bool:
        self.logger.info("=" * 60)
        self.logger.info("Starting Validation Pipeline")

        try:
            self._validate_database_connection()

            # Run validations
            is_valid = True

            if not self._validate_transactions():
                is_valid = False

            if not self._validate_identity():
                is_valid = False

            self._save_report()

            if is_valid:
                self.logger.info("Validation Pipeline completed successfully.")
                return True
            else:
                self.logger.error("Validation Pipeline failed due to data quality issues.")
                return False

        except Exception as e:
            self.logger.exception(f"Validation Pipeline failed: {e}")
            return False

    def _validate_database_connection(self) -> None:
        self.logger.info("Testing Database connection")
        if not self.database.test_connection():
            raise ConnectionError(
                "Could not connect to PostgreSQL. "
                "Check DATABASE_URL or ensure PostgreSQL is running."
            )
        self.logger.info("Database connection successful.")

    def _validate_transactions(self) -> bool:
        self.logger.info("Validating transaction table")
        table_name = constants.TRANSACTION_TABLE
        is_valid = True

        try:
            # Basic row count check
            query_count = f'SELECT COUNT(*) as count FROM "{table_name}"'
            count_df = pd.read_sql(query_count, self.database.get_engine())
            total_rows = int(count_df.iloc[0]["count"])
            self.logger.info(f"Total rows in {table_name}: {total_rows}")

            if total_rows == 0:
                self.logger.error(f"Table {table_name} is empty.")
                self.report_data[table_name] = {"status": "failed", "reason": "empty_table"}
                return False

            # Check for duplicates on TransactionID
            query_dupes = f"""
                SELECT "TransactionID", COUNT(*) as count 
                FROM "{table_name}" 
                GROUP BY "TransactionID" 
                HAVING COUNT(*) > 1
            """
            dupes_df = pd.read_sql(query_dupes, self.database.get_engine())
            dupes_count = len(dupes_df)

            # Check for nulls in critical columns
            query_nulls = f"""
                SELECT 
                    SUM(CASE WHEN "TransactionID" IS NULL THEN 1 ELSE 0 END) as null_ids,
                    SUM(CASE WHEN "isFraud" IS NULL THEN 1 ELSE 0 END) as null_targets
                FROM "{table_name}"
            """
            nulls_df = pd.read_sql(query_nulls, self.database.get_engine())
            null_ids = int(nulls_df.iloc[0]["null_ids"])
            null_targets = int(nulls_df.iloc[0]["null_targets"])

            self.report_data[table_name] = {
                "total_rows": total_rows,
                "duplicates_count": dupes_count,
                "null_transaction_ids": null_ids,
                "null_isfraud": null_targets,
                "status": "passed",
            }

            if dupes_count > 0:
                self.logger.error(f"Found {dupes_count} duplicate TransactionIDs in {table_name}")
                is_valid = False
                self.report_data[table_name]["status"] = "failed"

            if null_ids > 0:
                self.logger.error(f"Found {null_ids} NULL TransactionIDs in {table_name}")
                is_valid = False
                self.report_data[table_name]["status"] = "failed"

            if null_targets > 0:
                self.logger.error(f"Found {null_targets} NULL isFraud targets in {table_name}")
                is_valid = False
                self.report_data[table_name]["status"] = "failed"

            return is_valid

        except Exception as e:
            self.logger.error(f"Error validating {table_name}: {e}")
            self.report_data[table_name] = {"status": "error", "error_message": str(e)}
            return False

    def _validate_identity(self) -> bool:
        self.logger.info("Validating identity table")
        table_name = constants.IDENTITY_TABLE
        is_valid = True

        try:
            # Basic row count check
            query_count = f'SELECT COUNT(*) as count FROM "{table_name}"'
            count_df = pd.read_sql(query_count, self.database.get_engine())
            total_rows = int(count_df.iloc[0]["count"])
            self.logger.info(f"Total rows in {table_name}: {total_rows}")

            if total_rows == 0:
                self.logger.error(f"Table {table_name} is empty.")
                self.report_data[table_name] = {"status": "failed", "reason": "empty_table"}
                return False

            # Check for duplicates on TransactionID
            query_dupes = f"""
                SELECT "TransactionID", COUNT(*) as count 
                FROM "{table_name}" 
                GROUP BY "TransactionID" 
                HAVING COUNT(*) > 1
            """
            dupes_df = pd.read_sql(query_dupes, self.database.get_engine())
            dupes_count = len(dupes_df)

            # Check for nulls in critical columns
            query_nulls = f"""
                SELECT SUM(CASE WHEN "TransactionID" IS NULL THEN 1 ELSE 0 END) as null_ids
                FROM "{table_name}"
            """
            nulls_df = pd.read_sql(query_nulls, self.database.get_engine())
            null_ids = int(nulls_df.iloc[0]["null_ids"])

            self.report_data[table_name] = {
                "total_rows": total_rows,
                "duplicates_count": dupes_count,
                "null_transaction_ids": null_ids,
                "status": "passed",
            }

            if dupes_count > 0:
                self.logger.error(f"Found {dupes_count} duplicate TransactionIDs in {table_name}")
                is_valid = False
                self.report_data[table_name]["status"] = "failed"

            if null_ids > 0:
                self.logger.error(f"Found {null_ids} NULL TransactionIDs in {table_name}")
                is_valid = False
                self.report_data[table_name]["status"] = "failed"

            return is_valid

        except Exception as e:
            self.logger.error(f"Error validating {table_name}: {e}")
            self.report_data[table_name] = {"status": "error", "error_message": str(e)}
            return False

    def _save_report(self) -> None:
        self.logger.info(f"Saving validation report to {self.report_path}")
        try:
            with open(self.report_path, "w") as f:
                json.dump(self.report_data, f, indent=4)
        except Exception as e:
            self.logger.error(f"Failed to save validation report: {e}")
