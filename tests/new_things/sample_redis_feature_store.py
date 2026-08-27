import redis

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

print(r.ping())

features = {
    "avg_amount_90d": 842.31,
    "txn_count_24h": 7,
    "txn_count_7d": 31,
    "max_amount_30d": 12000.0,
    "unique_merchants_30d": 14,
}

customer_id = 12345

key = f"trie:features:v1:customer:{customer_id}"
r.hset(key, mapping=features)  # type: ignore

features = r.hgetall(key)
print(features)
