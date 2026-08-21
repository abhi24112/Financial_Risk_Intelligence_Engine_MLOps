# logging setup
from typing import Any

from database.connection import Database
from database.loader import CSVLoader
from pipelines.base_pipeline import BasePipeline
from shared import configure_logging, constants

configure_logging(log_file="ingestion_pipeline.log")


class IngestionPipeline(BasePipeline):
    """
    Pipeline responsible for ingesting raw CSV datasets
    into the PostgreSQL database.

    Responsibilities:
        - Verify database connectivity
        - Load raw datasets into PostgreSQL
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.database = Database()
        self.loader = CSVLoader(self.database)

    def _execute(self) -> dict[str, Any]:
        self._validate_database_connection()
        self._load_raw_data()

        return {"metadata": {"tables_loaded": len(constants.FILES_TO_TABLES)}}

    # Testing Database connection
    def _validate_database_connection(self) -> None:
        self.logger.info("Testing Database connection")
        if not self.database.test_connection():
            raise ConnectionError(
                "Could not connect to PostgreSQL. "
                "Check DATABASE_URL or ensure PostgreSQL is running."
            )
        self.logger.info("Database connection successful.")

    def _load_raw_data(self) -> None:
        self.logger.info(f"Loading {len(constants.FILES_TO_TABLES)} files into database")
        self.loader.load_many_csv(file_to_dict=constants.FILES_TO_TABLES)
        self.logger.info("Ingestion pipeline completed successfully")
