import logging
import os

from sqlalchemy import create_engine, text

from shared import configure_logging

configure_logging(log_file="database.log")


class Database:
    def __init__(self, database_url=None):
        self.database_url = database_url or os.getenv(
            "DATABASE_URL", "postgresql://fraud_user:admin@localhost:5432/fraud_risk"
        )
        self._engine = None
        logging.info("Database initialized Successfully")

    def get_engine(self):
        """
        This function helps to stablish the connection with psql

        # Input
        - database_url (DATABASE_URL)
        e.g : url = "postgresql://fraud_user:yourpassword@localhost:5432/fraud_risk"
        """
        if self._engine is None:
            logging.info("Creating new database engine...")
            self._engine = create_engine(self.database_url)
            logging.info("Database engine created successfully")
        else:
            logging.debug("Reusing existing database engine")

        return self._engine

    def test_connection(self) -> bool:
        logging.info("Testing database connection...")
        try:
            with self.get_engine().connect() as conn:
                logging.debug("Executing test query: SELECT 1")
                result = conn.execute(text("SELECT 1"))
                rows = result.fetchall()
                logging.info(f"Connection test successful. Result: {rows}")
            return True
        except Exception as e:
            logging.error(f"Connection Failed: {e}")
            return False
