"""流水线包装：Neo4j 不可用时自动降级为「通用模式」，保证服务不中断。

面试可讲点：
- RAG 系统必须考虑检索层故障。这里采用「降级而不是报错」策略：
  图谱挂了 → 用空检索结果继续走大模型，回答标注"未使用知识图谱"，
  用户仍能拿到回复，而不是看到 500。
- 这和 RAG 项目里「无 API Key 降级为纯检索」是同一套设计思想。
"""
import time

from agents.perception import perceive
from agents.diagnosis_agent import diagnose
from agents.report import generate_report
from neo4j_tools.retriever import _empty_result


def run_pipeline_safe(user_text: str, verbose: bool = False, engine: str = None) -> dict:
    """统一入口：按 engine 选 LangGraph 状态图或原四角色流水线。"""
    from fastapi_app.config import settings

    engine = engine or settings.AGENT_ENGINE
    if engine == "langgraph":
        try:
            from fastapi_app.graph_flow import run_graph
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
