import redis

r = redis.Redis(decode_responses=True)

# set / get
res1 = r.set("programming_lang", "python")
print(res1)
res2 = r.get("programming_lang")
print(res2)

# folder set/get
res3 = r.set("log:1", "setting up the folderset")
print(res3)
res4 = r.get("log:1")
print(res4)

# update values of key
res5 = r.set("programming_lang", "C++")
print(res5)

# NX and XX in Redis
res6 = r.set("bike:1", "bike", nx=True)
print(res6)  # None
print(r.get("bike:1"))  # Deimos
res7 = r.set("bike:1", "bike", xx=True)
print(res7)  # True

# mset and mget
res8 = r.mset({"bike:1": "Deimos", "bike:2": "Ares", "bike:3": "Vanth"})
print(res8)
res9 = r.mget(["bike:1", "bike:2", "bike:3"])
print(res9)

# INCR and INCRBY and INCRBYFLOAT
r.set("total_crashes", 0)
r.set("a", 2.19)
res10 = r.incr("total_crashes")
print(res10)  # 1
res11 = r.incrby("total_crashes", 10)
print(res11)  # 11
res11 = r.incrbyfloat("a", 1.3)
print(res11)  # 3.49
