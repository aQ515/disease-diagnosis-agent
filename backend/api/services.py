"""服务层：把智能体（agents/、neo4j_tools/）的能力封装成视图可调用的函数。

刻意保持「间接层」写法（_get_graph / _run_pipeline ...）：
视图层不直接 import 智能体模块，方便单元测试里 patch。

对外能力：
    health / graph_stats / graph_subgraph / symptoms
    retrieve_only / run_full / chat_once / reset_session
    evaluate        —— 创新点：双模式对照实验
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

from . import hallucination

logger = logging.getLogger(__name__)


class ServiceError(RuntimeError):
    """智能体运行异常，统一转成 502 返回前端。"""

    def __init__(self, message: str, stage: str = "unknown"):
        super().__init__(message)
        self.stage = stage


# ----------------------------- 间接层 -----------------------------


def _get_graph():
    from neo4j_tools.connection import get_graph

    return get_graph()


def _run_pipeline():
    from agents.pipeline import run_pipeline

    return run_pipeline


def _perceive():
    from agents.perception import perceive

    return perceive


def _graph_retrieve():
    from neo4j_tools.retriever import graph_retrieve

    return graph_retrieve


def _get_subgraph():
    from neo4j_tools.retriever import get_subgraph

    return get_subgraph


def _list_symptoms():
    from neo4j_tools.retriever import list_symptom_names

    return list_symptom_names


def _chat():
    from agents.chain import chat

    return chat


def _memory_clear():
    from agents.memory import memory_manager

    return memory_manager.clear


def _llm():
    from agents.llm import get_llm

    return get_llm


# ----------------------------- 图谱信息 -----------------------------


def graph_stats() -> Dict[str, Any]:
    """图谱规模统计。Neo4j 不通时返回 available=False（不抛错，前端顶部展示用）。"""
    try:
        graph = _get_graph()
        # 只统计疾病域（domain='disease'），与 PPT / 报告口径一致；
        # 同库中的设备故障图谱不混入标签与关系统计
        labels: List[Dict[str, Any]] = graph.run(
            "MATCH (n {domain:'disease'}) UNWIND labels(n) AS label "
            "RETURN label, count(*) AS count ORDER BY count DESC"
        ).data()
        rels: List[Dict[str, Any]] = graph.run(
            "MATCH (a {domain:'disease'})-[r]->(b {domain:'disease'}) "
            "RETURN type(r) AS type, count(*) AS count ORDER BY count DESC"
        ).data()
        total = graph.run("MATCH (n) RETURN count(n) AS c").data()[0]["c"]
        disease_total = graph.run(
            "MATCH (n {domain:'disease'}) RETURN count(n) AS c"
        ).data()[0]["c"]
        return {
            "available": True,
            "total_nodes": total,
            "disease_nodes": disease_total,
            "labels": labels,
            "relationships": rels,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("graph_stats 失败: %s", exc)
        return {
            "available": False,
            "message": str(exc),
            "total_nodes": 0,
            "disease_nodes": 0,
            "labels": [],
            "relationships": [],
        }


def symptoms() -> Dict[str, Any]:
    """症状词表（创新点：前端联想输入 + 口语归一校验）。"""
    try:
        lister = _list_symptoms()      # 间接层返回的是函数，再调用一次
        return {"symptoms": lister()}
    except Exception as exc:  # noqa: BLE001
        raise ServiceError(f"读取症状词表失败: {exc}", stage="retrieval") from exc


def graph_subgraph(name: str) -> Dict[str, Any]:
    """某疾病的一跳子图（创新点：前端手绘 SVG 可视化）。"""
    if not name:
        raise ServiceError("name 不能为空", stage="request")
    try:
        return _get_subgraph()(name)
    except Exception as exc:  # noqa: BLE001
        raise ServiceError(f"取子图失败: {exc}", stage="retrieval") from exc


# ----------------------------- 智能体能力 -----------------------------


def run_full(text: str, verbose: bool = False) -> Dict[str, Any]:
    """跑完整四角色流水线（慢，10~40 秒）。"""
    try:
        return _run_pipeline()(text, verbose=verbose)
    except Exception as exc:  # noqa: BLE001
        logger.exception("run_pipeline 失败")
        raise ServiceError(f"{type(exc).__name__}: {exc}", stage="pipeline") from exc


def retrieve_only(text: str) -> Dict[str, Any]:
    """只跑 感知 + 图谱检索（秒级、不烧 token），供前端「只查图谱」用。"""
    query: Dict[str, Any] = {"intent": "知识查询", "entities": {}, "raw": text}
    try:
        perceive = _perceive()
        graph_retrieve = _graph_retrieve()
    except Exception as exc:  # noqa: BLE001
        raise ServiceError(f"导入检索模块失败: {exc}", stage="import") from exc

    try:
        query = perceive(text)
    except Exception as exc:  # noqa: BLE001  感知失败降级为纯文本检索
        logger.warning("感知失败，降级为纯文本检索: %s", exc)

    try:
        data = graph_retrieve(query)
    except Exception as exc:  # noqa: BLE001
        raise ServiceError(f"Neo4j 检索失败: {exc}", stage="retrieval") from exc

    return {
        "input": text,
        "perception": query,
        "retrieval_hit": bool(data.get("hit")),
        "retrieval": data,
        "diagnosis": None,
        "report": None,
        "timing": {},
    }


def chat_once(text: str, session_id: str = "web") -> Dict[str, Any]:
    """带记忆的多轮对话（复用 agents/chain.py 的 MemoryManager，按 session 隔离）。"""
    try:
        chat = _chat()
    except Exception as exc:  # noqa: BLE001
        raise ServiceError(f"导入对话模块失败: {exc}", stage="import") from exc
    try:
        answer = chat(text, session_id=session_id)
    except Exception as exc:  # noqa: BLE001
        raise ServiceError(f"对话调用失败: {exc}", stage="chat") from exc
    return {"input": text, "session_id": session_id, "answer": answer}


def reset_session(session_id: str = "web") -> None:
    """清空某个会话的记忆。"""
    try:
        clear = _memory_clear()
    except Exception as exc:  # noqa: BLE001
        raise ServiceError(f"导入记忆模块失败: {exc}", stage="import") from exc
    clear(session_id)


# ----------------------------- 创新点：对照实验 -----------------------------


def _whitelist() -> set:
    """图谱白名单：所有实体名 + 疾病别名。用于判定「图谱外提及」。"""
    graph = _get_graph()
    names = set()
    for r in graph.run("MATCH (n {domain:'disease'}) RETURN n.name AS name, "
                       "n.alias1 AS a1, n.alias2 AS a2").data():
        for k in ("name", "a1", "a2"):
            if r.get(k):
                names.add(r[k])
    return names


def _plain_answer(question: str) -> str:
    """A 组：不给任何图谱信息，让大模型凭自己回答（对照组）。"""
    llm = _llm()(temperature=0.2)
    prompt = (
        "你是医疗助手。请回答下面的问题，给出可能疾病、处理建议和注意事项，300 字以内。\n\n"
        f"问题：{question}"
    )
    return llm.invoke(prompt).content


def _graph_answer(question: str) -> str:
    """B 组：走完整四角色流水线（图谱增强，实验组）。"""
    result = _run_pipeline()(question)
    return result.get("report") or ""


DEFAULT_QUESTIONS = [
    "我最近老是口渴、尿多，还瘦了，是不是糖尿病？",
    "头晕、心悸、头痛，需要看什么科？",
    "消渴病患者平时应该注意什么？",
]


def evaluate(questions: List[str] | None = None) -> Dict[str, Any]:
    """双模式对照实验：同一批问题，比较「纯大模型」与「图谱增强」的图谱外提及率。

    这是本项目最有说服力的实验：如果图谱增强把越界提及率显著压下来，
    就说明「先查图谱再让模型组织语言」这条路线确实能减少编造。
    """
    from django.conf import settings

    qs = [q for q in (questions or DEFAULT_QUESTIONS) if q and q.strip()]
    qs = qs[: settings.EVAL_QUESTIONS_LIMIT]
    if not qs:
        raise ServiceError("至少提供一个测试问题", stage="request")

    try:
        white = _whitelist()
    except Exception as exc:  # noqa: BLE001
        raise ServiceError(f"读取图谱白名单失败: {exc}", stage="retrieval") from exc

    rows: List[Dict[str, Any]] = []
    plain_illegal = graph_illegal = 0
    plain_total = graph_total = 0

    # 抽取用同一个模型实例（temperature=0 保证同一段文本抽出的实体稳定）
    try:
        extractor = _llm()(temperature=0.0)
    except Exception:  # noqa: BLE001
        extractor = None

    for q in qs:
        try:
            a_plain = _plain_answer(q)
        except Exception as exc:  # noqa: BLE001
            a_plain = f"[调用失败] {exc}"
        try:
            a_graph = _graph_answer(q)
        except Exception as exc:  # noqa: BLE001
            a_graph = f"[调用失败] {exc}"

        r_plain = hallucination.check(a_plain, white, llm=extractor)
        r_graph = hallucination.check(a_graph, white, llm=extractor)

        plain_illegal += r_plain["illegal_count"]
        plain_total += r_plain["total"]
        graph_illegal += r_graph["illegal_count"]
        graph_total += r_graph["total"]

        rows.append({
            "question": q,
            "plain": {"answer": a_plain, **r_plain},
            "graph": {"answer": a_graph, **r_graph},
        })

    def _rate(bad: int, all_: int) -> float:
        return round(bad / all_, 3) if all_ else 0.0

    return {
        "questions": rows,
        "summary": {
            "plain": {"mentions": plain_total, "illegal": plain_illegal,
                      "illegal_rate": _rate(plain_illegal, plain_total)},
            "graph": {"mentions": graph_total, "illegal": graph_illegal,
                      "illegal_rate": _rate(graph_illegal, graph_total)},
            "whitelist_size": len(white),
        },
        "note": "越界提及 = 回答里出现的药物/疾病名称不在知识图谱中，疑似编造。"
                "实体由大模型抽取（失败时回退规则抽取），越界率 = 越界数 / 提及总数。",
    }


# ----------------------------- 健康检查 -----------------------------


def health(probe_neo4j: bool = True) -> Dict[str, Any]:
    """探活：Django 自身、Neo4j、DashScope Key 是否就绪。

    probe_neo4j=False 时完全不碰 Neo4j —— 单测和无网环境用得上。
    """
    checks: Dict[str, Any] = {"django": {"ok": True, "detail": "api 已就绪"}}

    if probe_neo4j:
        t0 = time.time()
        try:
            _get_graph().run("RETURN 1").data()
            checks["neo4j"] = {
                "ok": True,
                "detail": f"连接正常 ({(time.time() - t0) * 1000:.0f} ms)",
            }
        except Exception as exc:  # noqa: BLE001
            checks["neo4j"] = {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}

    # 只读配置，不调用大模型，不消耗 token
    try:
        from config import config

        key = getattr(config, "DASHSCOPE_API_KEY", None) or ""
        checks["llm"] = {
            "ok": bool(key),
            "detail": "model=%s, key=%s" % (
                getattr(config, "QWEN_MODEL_NAME", "qwen-plus"),
                "已配置" if key else "未配置",
            ),
        }
    except Exception as exc:  # noqa: BLE001
        checks["llm"] = {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}

    return {
        "status": "ok" if all(c["ok"] for c in checks.values()) else "degraded",
        "service": "graph-disease-diagnosis-api",
        "version": "1.0.0",
        "checks": checks,
    }
