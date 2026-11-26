"""会话历史存储：本地 JSON 文件（session_id 隔离）。
不引入 MySQL——对 AI 应用岗意义不大，且会增加部署配置负担。
"""
import json
import os
import threading
from collections import defaultdict

from fastapi_app.config import settings

_lock = threading.Lock()


def _load() -> dict:
    if not os.path.exists(settings.HISTORY_FILE):
        return {}
    try:
        with open(settings.HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict):
    with open(settings.HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def append(session_id: str, question: str, answer: str, meta: dict | None = None):
    with _lock:
        data = _load()
        items = data.setdefault(session_id, [])
        items.append({
            "q": question,
            "a": answer,
            "ts": int(__import__("time").time()),
            "meta": meta or {},
        })
        # 每个会话只留最近 N 条
        data[session_id] = items[-settings.HISTORY_MAX:]
        _save(data)


def get_history(session_id: str) -> list:
    with _lock:
        return _load().get(session_id, [])


def clear(session_id: str):
    with _lock:
        data = _load()
        data.pop(session_id, None)
        _save(data)


def list_sessions() -> list:
    with _lock:
        data = _load()
        return [
            {"session_id": sid, "count": len(items), "last_ts": items[-1]["ts"] if items else 0}
            for sid, items in data.items()
        ]
