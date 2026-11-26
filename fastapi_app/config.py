"""FastAPI 版本配置：复用项目根 .env，新增 Redis / 缓存开关。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_ROOT, ".env"))


class Settings:
    # Redis（可选：没装 Redis 时自动降级为内存缓存，不影响启动）
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CACHE_TTL = int(os.getenv("CACHE_TTL", "600"))       # 缓存 10 分钟
    CACHE_ENABLED = os.getenv("CACHE_ENABLED", "1") == "1"

    # 历史记录存储（本地 JSON，MySQL 可后置）
    HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history.json")
    HISTORY_MAX = int(os.getenv("HISTORY_MAX", "50"))

    # 流式开关
    STREAM_CHUNK_DELAY = float(os.getenv("STREAM_CHUNK_DELAY", "0.012"))

    # Agent 引擎：pipeline（原四角色）/ langgraph（状态图编排）
    AGENT_ENGINE = os.getenv("AGENT_ENGINE", "langgraph")


settings = Settings()
