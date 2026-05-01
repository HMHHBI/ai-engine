import time


class MemoryRateLimiter:
    def __init__(self):
        self.store = {}

    def allow(self, user_id):
        now = time.time()

        count, timestamp = self.store.get(user_id, (0, now))

        if now - timestamp > 60:
            self.store[user_id] = (1, now)
            return True

        if count >= 20:
            return False

        self.store[user_id] = (count + 1, timestamp)
        return True