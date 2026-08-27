import redis

r = redis.Redis(decode_responses=True)

# Push in start and end
res1 = r.lpush("message", "ok")
res2 = r.lpush("message", "abhishek")

res3 = r.rpush("message", "this is added in the end")
res4 = r.rpush("message", "this is added in the starting")

print("res1: ", res1)
print("res2: ", res2)
print("res3: ", res3)
print("res4: ", res4)

# Multiple inputs
res5 = r.lpush("message", "hello", "bye", "will meet again")
print("res5: ", res5)

# print thelist
res5_list = r.lrange("message", 0, -1)
print(res5_list)

# pop the element from list
r.lpop("message")
print(r.lrange("message", 0, -1))
r.rpop("message")
print(r.lrange("message", 0, -1))

# Length of list
res5_length = r.llen("message")
print(res5_length)

# move from one list to another
res6 = r.lmove("bikes:repairs", "bikes:finished", "LEFT", "LEFT")
print(r.lrange("bikes:finished", 0, -1))

# trim a list
r.lpush("message", "hello", "bye", "will meet again")
print(r.lrange("message", 0, -1))
r.ltrim("message", 0, 2)
print(r.lrange("message", 0, -1))
