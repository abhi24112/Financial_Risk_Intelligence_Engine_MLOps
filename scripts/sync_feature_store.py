import argparse
import logging
import os
import sys
from pathlib import Path

import pandas as pd

# Add project root to Python path
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from database.redis_client import RedisClient  # noqa: E402
from shared import configure_logging, constants  # noqa: E402

configure_logging(log_file="sync_feature_store.log")


def sync_features_to_redis(limit: int = None):  # type: ignore
    """
    Reads the engineered features parquet file, gets the most recent state
    for each customer (uid_card), and pushes it to Redis.
    """
    logger = logging.getLogger(__name__)
    redis_client = RedisClient()

    if not redis_client.client:
        logger.error("Could not connect to Redis. Sync aborted.")
        return

    features_path = os.path.join(constants.PROCESSED_DATASET_DIR, "features.parquet")
    if not os.path.exists(features_path):
        logger.error(f"Features file not found at {features_path}. Run feature engineering first.")
        return

    logger.info(f"Loading {features_path}...")
    df = pd.read_parquet(features_path)

    if "uid_card" not in df.columns:
        logger.error("uid_card not found in features. Cannot sync to Redis.")
        return

    # We want the LATEST state of the customer.
    # Since the dataframe was sorted by TransactionDT in feature engineering,
    # dropping duplicates and keeping the 'last' occurrence gives us their current state.
    logger.info("Extracting latest profiles per customer...")
    latest_profiles = df.drop_duplicates(subset=["uid_card"], keep="last")

    if limit:
        latest_profiles = latest_profiles.head(limit)

    logger.info(f"Syncing {len(latest_profiles)} customer profiles to Redis...")

    # List of features we want to cache in Redis
    feature_cols = [
        "identity_transaction_count",
        "identity_avg_amount",
        "TransactionDT",
        "transactions_last_24h",
        "amount_last_24h",
        "is_new_email",
        "is_new_device",
    ]

    # caching columns that actually exist
    valid_cols = [col for col in feature_cols if col in latest_profiles.columns]

    success_count = 0
    for _, row in latest_profiles.iterrows():
        uid = row["uid_card"]
        key = f"customer_profile:{uid}"

        profile = {col: row[col] for col in valid_cols}

        if redis_client.set_feature_profile(key, profile):
            success_count += 1

    logger.info(f"Successfully synced {success_count}/{len(latest_profiles)} profiles to Redis.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync offline features to Redis Online Feature Store.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of profiles to sync (for testing)")
    args = parser.parse_args()

    sync_features_to_redis(limit=args.limit)
