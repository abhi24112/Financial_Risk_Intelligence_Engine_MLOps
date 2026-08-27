import logging
import os
from typing import Any, cast

import pandas as pd
import redis

from shared import configure_logging

configure_logging(log_file="redis_client.log")


class RedisClient:
    """
    Singleton wrapper for Redis connection to ensure connection pooling
    and safe read/writes for the Online Feature Store.
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        if self._initialized:
            return

        redis_url = os.getenv("REDIS_URL", f"redis://{host}:{port}/{db}")
        logging.info(f"Connecting to Redis at {redis_url}...")

        try:
            self.client = redis.Redis.from_url(
                redis_url,
                decode_responses=True,  # Automatically decodes byte strings to Python strings
                socket_timeout=1.0,  # Critical for <100ms SLA, fail fast if Redis is down
            )
            self.client.ping()
            logging.info("Redis connection established successfully.")
            self._initialized = True
        except redis.ConnectionError as e:
            logging.error(f"Failed to connect to Redis: {e}")
            self.client = None

    def set_feature_profile(self, entity_id: str, profile: dict[str, Any], ttl_seconds: int | None = None) -> bool:
        """Saves a feature dictionary to Redis as a Hash."""
        if not self.client:
            return False

        try:
            # We use Redis Hashes (HSET) because they are memory efficient and allow fetching specific fields
            # Convert values to strings for Redis Hash compatibility
            stringified_profile = {str(k): str(v) for k, v in profile.items() if pd.notna(v)}

            if stringified_profile:
                # Use pipeline for atomic write
                pipe = self.client.pipeline()
                pipe.hset(entity_id, mapping=cast(dict[Any, Any], stringified_profile))
                if ttl_seconds:
                    pipe.expire(entity_id, ttl_seconds)
                pipe.execute()
            return True
        except Exception as e:
            logging.error(f"Error saving profile for {entity_id}: {e}")
            return False

    def get_feature_profile(self, entity_id: str) -> dict[str, str]:
        """Retrieves the feature Hash for a given entity."""
        if not self.client:
            return {}

        try:
            return self.client.hgetall(entity_id)  # type: ignore
        except Exception as e:
            logging.error(f"Error retrieving profile for {entity_id}: {e}")
            return {}
