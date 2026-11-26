"""LangGraph 编排：意图识别 → 条件分支检索 → 诊断 → 报告 → END。

用 StateGraph 显式建模节点与条件边：
- 条件路由：查药意图 → RAG 检索 / 查症状意图 → Neo4j 图谱 / 闲聊 → 直接对话
- 状态贯穿：每一步写入 AgentState，便于观测与回溯
"""
import os
import sys
import time
from typing import TypedDict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langgraph.graph import StateGraph, END

from agents.perception import perceive
from agents.diagnosis_agent import diagnose
from agents.report import generate_report
from neo4j_tools.retriever import graph_retrieve, _empty_result


class AgentState(TypedDict, total=False):
    question: str
    intent: str
    entities: dict
    retrieval: dict
    route: str
    diagnosis: dict
    report: str
    timing: dict
    trace: list


def _stamp(state: AgentState, step: str, t0: float):
    state.setdefault("trace", []).append({"step": step, "ms": round((time.time() - t0) * 1000)})


# ---------- 节点 ----------

def node_perception(state: AgentState) -> AgentState:
    t0 = time.time()
    q = perceive(state["question"])
    state["intent"] = q.get("intent", "闲聊")
    state["entities"] = q.get("entities", {})
    _stamp(state, "perception", t0)
    return state


def route_by_intent(state: AgentState) -> str:
    """条件边：根据意图 + 实体决定走哪条检索路径。"""
    if state["intent"] == "闲聊" and not state["entities"].get("symptom"):
        return "chitchat"
    # 提到药品/用药 → RAG；否则症状/疾病 → 知识图谱
    text = state["question"]
    if any(w in text for w in ["药", "吃", "剂量", "副作用"]):
        return "rag"
    return "graph"


def node_graph(state: AgentState) -> AgentState:
    t0 = time.time()
    try:
        state["retrieval"] = graph_retrieve({
            "intent": state["intent"],
            "entities": state["entities"],
            "raw": state["question"],
        })
        state["route"] = "neo4j"
    except Exception as e:
        state["retrieval"] = _empty_result(f"图谱不可用：{str(e)[:60]}")
        state["route"] = "neo4j-fallback"
    _stamp(state, "retrieval", t0)
    return state


def node_rag(state: AgentState) -> AgentState:
    """药品相关走 RAG：复用 Medical-RAG-QA 的检索能力（若可用）。
    当前项目未内置该模块，降级为图谱 + 文本兜底，保证流程不断。"""
    t0 = time.time()
    try:
        state["retrieval"] = graph_retrieve({
            "intent": state["intent"],
            "entities": state["entities"],
            "raw": state["question"],
        })
        state["route"] = "rag(graph-backed)"
    except Exception:
        state["retrieval"] = _empty_result("RAG 检索暂不可用")
        state["route"] = "rag-fallback"
    _stamp(state, "retrieval", t0)
    return state


def node_chitchat(state: AgentState) -> AgentState:
    t0 = time.time()
    state["retrieval"] = _empty_result("闲聊，无需检索")
    state["route"] = "chitchat"
    _stamp(state, "retrieval", t0)
    return state


def node_diagnose(state: AgentState) -> AgentState:
    t0 = time.time()
    state["diagnosis"] = diagnose(state["question"], retrieval=state["retrieval"])
    _stamp(state, "diagnosis", t0)
    return state


def node_report(state: AgentState) -> AgentState:
    t0 = time.time()
    state["report"] = generate_report(state["diagnosis"])
    _stamp(state, "report", t0)
    return state


# ---------- 建图 ----------

def build_graph():
    g = StateGraph(AgentState)
    g.add_node("perception", node_perception)
    g.add_node("graph", node_graph)
    g.add_node("rag", node_rag)
    g.add_node("chitchat", node_chitchat)
    g.add_node("diagnose", node_diagnose)
    g.add_node("report", node_report)

    g.set_entry_point("perception")
    g.add_conditional_edges(
        "perception",
        route_by_intent,
        {"graph": "graph", "rag": "rag", "chitchat": "chitchat"},
    )
    # 三条检索路径汇合到诊断
    g.add_edge("graph", "diagnose")
    g.add_edge("rag", "diagnose")
    g.add_edge("chitchat", "diagnose")
    g.add_edge("diagnose", "report")
    g.add_edge("report", END)
    return g.compile()


app = build_graph()


def run_graph(question: str) -> dict:
    t0 = time.time()
    final = app.invoke({
        "question": question,
        "trace": [],
    })
    return {
        "input": question,
        "intent": final.get("intent"),
        "route": final.get("route"),
        "retrieval": final.get("retrieval", {}),
        "diagnosis": final.get("diagnosis", {}),
        "report": final.get("report", ""),
        "trace": final.get("trace", []),
        "timing": {"total_s": round(time.time() - t0, 2)},
        "engine": "langgraph",
    }


if __name__ == "__main__":
    out = run_graph("我最近老是口渴、尿多，还瘦了")
    print("路由:", out["route"], "| 意图:", out["intent"])
    print("轨迹:", out["trace"])
    print("报告:", out["report"][:200])
