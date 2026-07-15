from database.connection import Database
from database.loader import CSVLoader

FILES_TO_TABLES = {
    "dataset/raw/train_transaction.csv": "train_transaction",
    "dataset/raw/train_identity.csv": "train_identity",
    "dataset/raw/test_transaction.csv": "test_transaction",
    "dataset/raw/test_identity.csv": "test_identity",
}

if __name__ == "__main__":
    db = Database()

    # Testing Database connection
    if not db.test_connection():
        raise ConnectionError(
            "Could not connect to database - Check Database_URL / Postgres is running"
        )

    loader = CSVLoader(db)
    loader.load_many_csv(file_to_dict=FILES_TO_TABLES)
