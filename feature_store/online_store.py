import logging

from database.redis_client import RedisClient


class OnlineFeatureStore:
    """
    Business logic layer for retrieving features from the Redis backend.
    Handles 'Cold Start' logic if a user is not found in the store.
    """

    def __init__(self):
        self.redis = RedisClient()
        self.logger = logging.getLogger(__name__)

    def get_customer_profile(self, uid_card: str) -> dict[str, float]:
        """
        Fetches the latest aggregated behavioral stats for a customer.
        Returns a dictionary of float values.
        """
        key = f"customer_profile:{uid_card}"
        raw_profile = self.redis.get_feature_profile(key)

        # Parse the strings back to floats
        parsed_profile = {}
        for k, v in raw_profile.items():
            try:
                parsed_profile[k] = float(v)
            except ValueError:
                pass  # Skip non-numeric features if any accidentally got in

        # Handle Cold Start Problem (Brand new customer)
        if not parsed_profile:
            self.logger.debug(f"Cold start for {uid_card}, returning default profile.")
            return self._get_default_profile()

        return parsed_profile

    def _get_default_profile(self) -> dict[str, float]:
        """
        Returns default fallback values for brand new customers
        so the model doesn't fail on missing data.
        """
        return {
            "identity_transaction_count": 0.0,
            "identity_avg_amount": 0.0,
            "amount_vs_identity_avg": 0.0,
            "time_since_last_transaction": -1.0,
            "transactions_last_24h": 0.0,
            "amount_last_24h": 0.0,
            "is_new_email": 1.0,
            "is_new_device": 1.0,
        }
