"""高频问答缓存：Redis 优先，连不上时自动降级为进程内字典。

面试可讲点：
- 缓存键用「问题文本」的 md5，命中直接返回，省掉一次完整 Agent 流水线（约 3-6 秒 → 毫秒级）
- Redis 不可用时不影响主流程，这是生产环境常见降级策略
"""
import hashlib
import json
import threading
import time
from typing import Optional

from fastapi_app.config import settings

try:
    import redis as redis_lib
except ImportError:
    redis_lib = None


def _key(question: str) -> str:
    return "agent:qa:" + hashlib.md5(question.strip().encode("utf-8")).hexdigest()


class MemoryCache:
    def __init__(self):
        self._data = {}
        self._lock = threading.Lock()

    def get(self, k: str) -> Optional[dict]:
        with self._lock:
            item = self._data.get(k)
            if not item:
                return None
            if item["expire"] < time.time():
                self._data.pop(k, None)
                return None
            return item["value"]

    def set(self, k: str, v: dict, ttl: int):
        with self._lock:
            self._data[k] = {"value": v, "expire": time.time() + ttl}


class RedisCache:
    def __init__(self, url: str):
        self._client = redis_lib.Redis.from_url(url, decode_responses=True, socket_timeout=1)

    def get(self, k: str) -> Optional[dict]:
        raw = self._client.get(k)
        return json.loads(raw) if raw else None

    def set(self, k: str, v: dict, ttl: int):
        self._client.setex(k, ttl, json.dumps(v, ensure_ascii=False))


class CacheStore:
    """对外统一接口，内部自动选 Redis 或内存。"""

    def __init__(self):
        self.backend = None
        self.backend_name = "disabled"
        if not settings.CACHE_ENABLED:
            return
        if redis_lib:
            try:
                candidate = RedisCache(settings.REDIS_URL)
                candidate._client.ping()
                self.backend = candidate
                self.backend_name = "redis"
                return
            except Exception:
                pass
        self.backend = MemoryCache()
        self.backend_name = "memory"

    def get(self, question: str) -> Optional[dict]:
        if not self.backend:
            return None
        try:
            return self.backend.get(_key(question))
        except Exception:
            return None

    def set(self, question: str, value: dict):
        if not self.backend:
            return
        try:
            self.backend.set(_key(question), value, settings.CACHE_TTL)
        except Exception:
            pass


cache = CacheStore()
