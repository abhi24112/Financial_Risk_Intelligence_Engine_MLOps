import io
import logging

import pandas as pd
import psycopg2

from database.connection import Database
from shared.constants import constants


class CSVLoader:
    def __init__(self, db: Database, chunksize: int = constants.DEFAULT_CHUNK_SIZE):
        self.db = db
        self.chunksize = chunksize

    def load_csv(self, filepath: str, table_name: str):
        """Load a CSV file into a PostgreSQL table using psycopg2 COPY FROM STDIN.

        This approach bypasses SQLAlchemy and pandas to_sql entirely, making it
        compatible with any combination of pandas / SQLAlchemy versions and is
        also significantly faster for bulk loads (uses PostgreSQL COPY protocol).
        """
        logging.info(f"Loading {filepath} -> {table_name}")

        # Parse connection params from the URL
        db_url = self.db.database_url  # e.g. postgresql://user:pass@host:port/db

        conn = psycopg2.connect(db_url)
        cursor = None
        try:
            cursor = conn.cursor()
            first_chunk = True

            for i, chunk in enumerate(pd.read_csv(filepath, chunksize=self.chunksize)):
                # On first chunk: create/replace the table using CREATE TABLE AS with zero rows
                if first_chunk:
                    # Build CREATE TABLE statement from dtypes
                    self._create_table(cursor, conn, chunk, table_name)
                    first_chunk = False

                # Use COPY FROM STDIN — fastest bulk insert method for PostgreSQL
                buf = io.StringIO()
                chunk.to_csv(buf, index=False, header=False, na_rep="\\N")
                buf.seek(0)
                cursor.copy_expert(
                    f"COPY {table_name} FROM STDIN WITH (FORMAT CSV, NULL '\\N')",
                    buf,
                )
                conn.commit()
                logging.info(f"Loaded chunk {i + 1} into {table_name}")

        finally:
            if cursor is not None:
                cursor.close()
            conn.close()

        logging.info(f"Done: {table_name}")

    def _create_table(self, cursor, conn, chunk: pd.DataFrame, table_name: str):
        """Drop-and-recreate target table with schema derived from the first chunk."""
        dtype_map = {
            "int64": "BIGINT",
            "int32": "INTEGER",
            "int16": "SMALLINT",
            "float64": "DOUBLE PRECISION",
            "float32": "REAL",
            "bool": "BOOLEAN",
            "object": "TEXT",
            "datetime64[ns]": "TIMESTAMP",
        }
        col_defs = []
        for col, dtype in chunk.dtypes.items():
            pg_type = dtype_map.get(str(dtype), "TEXT")
            col_defs.append(f'"{col}" {pg_type}')

        cursor.execute(f'DROP TABLE IF EXISTS "{table_name}"')
        cursor.execute(f'CREATE TABLE "{table_name}" ({", ".join(col_defs)})')
        conn.commit()
        logging.info(f"Created table {table_name} with {len(col_defs)} columns")

    def load_many_csv(self, file_to_dict: dict[str, str]):
        logging.info(f"Loading {len(file_to_dict)} CSV files")
        for filepath, table_name in file_to_dict.items():
            self.load_csv(filepath, table_name)
        logging.info("All CSV files loaded successfully")
