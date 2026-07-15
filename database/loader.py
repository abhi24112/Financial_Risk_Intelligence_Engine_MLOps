import pandas as pd

from database.connection import Database


class CSVLoader:
    def __init__(self, db: Database, chunksize: int = 50_000):
        self.db = db
        self.chunksize = chunksize

    def load_csv(self, filepath: str, table_name: str):
        engine = self.db.get_engine()
        print(f"Loading {filepath} -> {table_name}")
        for i, chunk in enumerate(pd.read_csv(filepath, chunksize=self.chunksize)):
            chunk.to_sql(table_name, engine, index=False, if_exists="append" if i else "replace")
        print(f"Done: {table_name}")

    def load_many_csv(self, file_to_dict: dict[str, str]):
        for filepath, table_name in file_to_dict.items():
            self.load_csv(filepath, table_name)
