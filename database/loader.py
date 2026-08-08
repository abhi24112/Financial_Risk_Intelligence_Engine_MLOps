import logging

import pandas as pd

from database.connection import Database
from shared import configure_logging
from shared.constants import constants

configure_logging(log_file="database.log")


class CSVLoader:
    def __init__(self, db: Database, chunksize: int = constants.DEFAULT_CHUNK_SIZE):
        self.db = db
        self.chunksize = chunksize

    def load_csv(self, filepath: str, table_name: str):
        engine = self.db.get_engine()
        logging.info(f"Loading {filepath} -> {table_name}")
        for i, chunk in enumerate(pd.read_csv(filepath, chunksize=self.chunksize)):
            chunk.to_sql(table_name, engine, index=False, if_exists="append" if i else "replace")
            logging.info(f"Loaded chunk {i+1} into {table_name}")
        logging.info(f"Done: {table_name}")

    def load_many_csv(self, file_to_dict: dict[str, str]):
        logging.info(f"Loading {len(file_to_dict)} CSV files")
        for filepath, table_name in file_to_dict.items():
            self.load_csv(filepath, table_name)
        logging.info("All CSV files loaded successfully")
