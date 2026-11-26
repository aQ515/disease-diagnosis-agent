"""医疗 AI 导诊助手 · FastAPI 版

启动：uvicorn backend.main:app --reload --port 8002

接口：
- POST /chat          SSE 流式问答（打字机效果）
- GET  /history/{sid} 会话历史
- DELETE /history/{sid} 清空会话
- GET  /api/health    探活（neo4j / llm / cache）
- GET  /              前端页面

设计要点（面试可讲）：
1. SSE 流式：先跑完整流水线拿到结构化结果，再把 report 按字符切片逐步推送，
   前端实现打字机效果；同时每个阶段（感知/检索/诊断/报告）单独推送事件，用户能看到进度。
2. 缓存：命中缓存直接流式吐出历史答案，跳过 3-6 秒的 Agent 流水线。
3. 安全护栏：复用原项目的 guard_dosage，流式输出前已处理完，不会把编造剂量吐出去。
"""
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.pipeline import run_pipeline_safe
from agents.report import guard_dosage
from backend.cache import cache
from backend import history
from backend.config import settings

app = FastAPI(title="医疗 AI 导诊助手", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    question: str
    session_id: str = "default"
    use_cache: bool = True


@app.get("/")
def index():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "index.html")
    if os.path.exists(path):
        return FileResponse(path)
    return HTMLResponse("<h1>医疗 AI 导诊助手</h1><p>前端页面未找到</p>")


@app.get("/api/engine")
def engine_info():
    from backend.config import settings
    return {"configured": settings.AGENT_ENGINE, "langgraph_available": _langgraph_ok()}


def _langgraph_ok() -> bool:
    try:
        from backend.graph_flow import app as graph_app
        return graph_app is not None
    except Exception:
        return False


@app.get("/api/health")
def health():
    result = {"api": "ok", "cache": cache.backend_name, "engine": settings.AGENT_ENGINE}
    try:
        from neo4j_tools.connection import get_graph
        g = get_graph()
        g.run("RETURN 1 AS x").data()
        result["neo4j"] = "ok"
    except Exception as e:
        result["neo4j"] = f"error: {str(e)[:80]}"
    try:
        from agents.llm import get_llm
        get_llm()
        result["llm"] = "ok"
    except Exception as e:
        result["llm"] = f"error: {str(e)[:80]}"
    return result


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/chat")
async def chat(req: ChatRequest):
    if not req.question.strip():
        raise HTTPException(400, "问题不能为空")

    async def stream():
        t0 = time.time()
        hit_cache = False
        payload = None
        engine_meta = {}

        # 1. 缓存命中：直接吐历史答案
        if req.use_cache:
            cached = cache.get(req.question)
            if cached:
                hit_cache = True
                payload = cached
                yield _sse("stage", {"name": "cache", "msg": "命中缓存，秒级返回"})

        # 2. 未命中：跑完整 Agent 流水线（放到线程里，避免阻塞事件循环）
        if payload is None:
            yield _sse("stage", {"name": "perception", "msg": "正在理解你的问题…"})
            try:
                result = await asyncio.to_thread(run_pipeline_safe, req.question)
            except Exception as e:
                # 降级：数据库/模型任一不可用时，不直接断流（前端会卡住），
                # 而是吐出 error 事件 + 可读提示，让前端能收尾。
                msg = str(e).replace("\n", " ")[:160]
                yield _sse("error", {"msg": "服务暂时不可用", "detail": msg})
                yield _sse("done", {
                    "session_id": req.session_id,
                    "cached": False,
                    "elapsed_s": round(time.time() - t0, 2),
                    "sources": [],
                    "intent": None,
                    "confidence": None,
                    "error": msg,
                })
                return

            engine_meta = {
                "engine": result.get("engine", "pipeline"),
                "route": result.get("route"),
                "trace": result.get("trace"),
            }
            perception = result.get("perception", {})
            retrieval = result.get("retrieval", {})
            diag = result.get("diagnosis", {})
            report = result.get("report", "")

            # 保险：流式前再过一次剂量护栏
            report = guard_dosage(report, retrieval)

            yield _sse("stage", {
                "name": "retrieval",
                "msg": f"检索 {'命中' if retrieval.get('hit') else '未命中'} 图谱",
                "detail": {
                    "intent": perception.get("intent"),
                    "mode": retrieval.get("mode"),
                    "disease": (retrieval.get("disease") or {}).get("name"),
                    "confidence": diag.get("confidence"),
                },
            })

            payload = {
                "report": report,
                "perception": perception,
                "retrieval": retrieval,
                "diagnosis": diag,
                "timing": result.get("timing", {}),
                "degraded": result.get("degraded", False),
            }
            cache.set(req.question, payload)

        # 3. 流式吐报告（打字机效果）
        yield _sse("stage", {"name": "report", "msg": "正在生成报告…"})
        report = payload.get("report", "")
        # 按小段切片：中文按 2 字一段，视觉上像打字机
        step = 2
        for i in range(0, len(report), step):
            yield _sse("token", {"text": report[i:i + step]})
            await asyncio.sleep(settings.STREAM_CHUNK_DELAY)

        # 4. 完成事件：带元数据和来源
        sources = []
        d = (payload.get("retrieval", {}).get("disease") or {})
        if d.get("name"):
            sources.append({"type": "知识图谱", "name": d["name"], "alias": d.get("alias1")})
        for ev in (payload.get("diagnosis", {}).get("evidence") or [])[:3]:
            sources.append({"type": "图谱依据", "text": str(ev)})

        final = {
            "session_id": req.session_id,
            "cached": hit_cache,
            "elapsed_s": round(time.time() - t0, 2),
            "sources": sources,
            "intent": payload.get("perception", {}).get("intent"),
            "confidence": payload.get("diagnosis", {}).get("confidence"),
            "timing": payload.get("timing", {}),
            "degraded": payload.get("degraded", False),
            "engine": engine_meta.get("engine", "pipeline"),
            "route": engine_meta.get("route"),
            "trace": engine_meta.get("trace"),
        }
        yield _sse("done", final)

        history.append(req.session_id, req.question, report, {
            "cached": hit_cache,
            "sources": sources,
            "confidence": final.get("confidence"),
        })

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/history/{session_id}")
def get_history(session_id: str):
    return {"session_id": session_id, "items": history.get_history(session_id)}


@app.delete("/history/{session_id}")
def delete_history(session_id: str):
    history.clear(session_id)
    return {"ok": True, "session_id": session_id}


@app.get("/sessions")
def list_sessions():
    return {"sessions": history.list_sessions()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8002, reload=True)
