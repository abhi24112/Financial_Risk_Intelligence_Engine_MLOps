import os

from sqlalchemy import create_engine, text


class Database:
    def __init__(self, database_url=None):
        self.database_url = database_url or os.getenv(
            "DATABASE_URL", "postgresql://fraud_user:admin@localhost:5432/fraud_risk"
        )
        self._engine = None

    def get_engine(self):
        """
        This function helps to stablish the connection with psql

        # Input
        - database_url (DATABASE_URL)
        e.g : url = "postgresql://fraud_user:yourpassword@localhost:5432/fraud_risk"
        """
        if self._engine is None:
            self._engine = create_engine(self.database_url)

        return self._engine

    def test_connection(self) -> bool:
        try:
            with self.get_engine().connect() as conn:
                result = conn.execute(text("SELECT 1"))
                rows = result.fetchall()
                print(rows)
            return True
        except Exception as e:
            print(f"Connection Failed: {e}")
            return False
