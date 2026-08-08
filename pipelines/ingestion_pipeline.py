# logging setup
import logging

from database.connection import Database
from database.loader import CSVLoader
from shared import configure_logging, constants

configure_logging(log_file="pipeline.log")


class IngestionPipeline:
    """
    Pipeline responsible for ingesting raw CSV datasets
    into the PostgreSQL database.

    Responsibilities:
        - Verify database connectivity
        - Load raw datasets into PostgreSQL
        - Log pipeline execution
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.database = Database()
        self.loader = CSVLoader(self.database)

    def run(self) -> bool:
        self.logger.info("=" * 60)
        self.logger.info("Starting Ingestion Pipeline")

        try:
            self._validate_database_connection()
            self._load_raw_data()

            self.logger.info("Ingestion Pipeline completed successfully.")
            return True

        except Exception as e:
            self.logger.exception(f"Ingestion Pipeline failed: {e}")
            return False

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
