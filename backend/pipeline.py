"""流水线包装：Neo4j 不可用时降级为通用模式，避免请求失败。

检索层故障时用空结果继续走大模型，回答中标注未使用知识图谱。
"""
import time

from agents.perception import perceive
from agents.diagnosis_agent import diagnose
from agents.report import generate_report
from neo4j_tools.retriever import _empty_result


def run_pipeline_safe(user_text: str, verbose: bool = False, engine: str = None) -> dict:
    """统一入口：按 engine 选 LangGraph 状态图或原四角色流水线。"""
    from backend.config import settings

    engine = engine or settings.AGENT_ENGINE
    if engine == "langgraph":
        try:
            from backend.graph_flow import run_graph
            result = run_graph(user_text)
            result["degraded"] = False
            return result
        except Exception:
            # LangGraph 不可用时回退到原流水线（保证服务不中断）
            pass

    t0 = time.time()
    query = perceive(user_text)

    try:
        from agents.pipeline import run_pipeline
        result = run_pipeline(user_text, verbose=verbose)
        result["degraded"] = False
        return result
    except Exception as e:
        # 图谱不可用：空检索结果继续走诊断 + 报告
        empty = _empty_result(f"知识图谱暂不可用，已切换通用模式（{str(e)[:60]}）")
        diag = diagnose(user_text, retrieval=empty)
        report = generate_report(diag)
        return {
            "input": user_text,
            "perception": query,
            "retrieval_hit": False,
            "retrieval": empty,
            "diagnosis": diag,
            "report": report,
            "degraded": True,
            "timing": {"total_s": round(time.time() - t0, 2)},
        }
