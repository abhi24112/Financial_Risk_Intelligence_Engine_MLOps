import time

import redis

r = redis.Redis(decode_responses=True)
res1 = r.hset(
    "bike:1",
    mapping={
        "model": "Deimos",
        "brand": "Ergonom",
        "type": "Enduro bikes",
        "price": 4972,
    },
)
print(res1)
# >>> 4

res2 = r.hget("bike:1", "model")
print(res2)
# >>> 'Deimos'

res3 = r.hget("bike:1", "price")
print(res3)
# >>> '4972'

res4 = r.hgetall("bike:1")
print(res4)
# >>> {'model': 'Deimos', 'brand': 'Ergonom', 'type': 'Enduro bikes', 'price': '4972'}


# Recreate the bike:1 hash so this example runs on its own.
r.delete("bike:1")
r.hset(
    "bike:1",
    mapping={
        "model": "Deimos",
        "brand": "Ergonom",
        "type": "Enduro bikes",
        "price": 4972,
    },
)

res5 = r.hmget("bike:1", ["model", "price"])
print(res5)
# >>> ['Deimos', '4972']


# Recreate the bike:1 hash so this example runs on its own.
r.delete("bike:1")
r.hset(
    "bike:1",
    mapping={
        "model": "Deimos",
        "brand": "Ergonom",
        "type": "Enduro bikes",
        "price": 4972,
    },
)

res6 = r.hincrby("bike:1", "price", 100)
print(res6)
# >>> 5072
res7 = r.hincrby("bike:1", "price", -100)
print(res7)
# >>> 4972


res11 = r.hincrby("bike:1:stats", "rides", 1)
print(res11)
# >>> 1
res12 = r.hincrby("bike:1:stats", "rides", 1)
print(res12)
# >>> 2
res13 = r.hincrby("bike:1:stats", "rides", 1)
print(res13)
# >>> 3
res14 = r.hincrby("bike:1:stats", "crashes", 1)
print(res14)
# >>> 1
res15 = r.hincrby("bike:1:stats", "owners", 1)
print(res15)
# >>> 1
res16 = r.hget("bike:1:stats", "rides")
print(res16)
# >>> 3
res17 = r.hmget("bike:1:stats", ["crashes", "owners"])
print(res17)
# >>> ['1', '1']


r.delete("sensor:sensor1")
r.hset("sensor:sensor1", mapping={"air_quality": 256, "battery_level": 89})

# Set a TTL of 60 seconds on two fields of the hash.
res18 = r.hexpire("sensor:sensor1", 60, "air_quality", "battery_level")
print(res18)
# >>> [1, 1]

# Retrieve the remaining TTL for those fields.
res19 = r.httl("sensor:sensor1", "air_quality", "battery_level")
print(res19)
# >>> [60, 60]
# (your actual values may be slightly lower)


r.delete("sensor:sensor1")
r.hset("sensor:sensor1", mapping={"air_quality": 256, "battery_level": 89})

# Set the TTL of the 'air_quality' field in milliseconds.
res20 = r.hpexpire("sensor:sensor1", 60000, "air_quality")
print(res20)
# >>> [1]

# Retrieve the remaining TTL in milliseconds.
res21 = r.hpttl("sensor:sensor1", "air_quality")
print(res21)
# >>> [59994]
# (your actual value may vary)


r.delete("sensor:sensor1")
r.hset("sensor:sensor1", mapping={"air_quality": 256, "battery_level": 89})

# Set the expiration of 'air_quality' to a Unix time 24 hours from now.
res22 = r.hexpireat(
    "sensor:sensor1",
    int(time.time()) + 24 * 60 * 60,
    "air_quality",
)
print(res22)
# >>> [1]

# Retrieve the expiration time as a Unix timestamp in seconds.
res23 = r.hexpiretime("sensor:sensor1", "air_quality")
print(res23)
# >>> [1717668041]
# (your actual value will vary)
