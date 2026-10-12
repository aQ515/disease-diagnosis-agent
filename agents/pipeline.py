"""四角色流水线：感知 → 图谱检索 → 诊断 → 报告。

修复了原版的「重复检索」问题：检索结果直接传给诊断角色，
诊断角色不再通过工具二次检索（可通过 use_agent=True 切回工具调用模式）。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.perception import perceive
from agents.diagnosis_agent import diagnose
from agents.report import generate_report
from neo4j_tools.retriever import graph_retrieve


def run_pipeline(user_text: str, verbose: bool = False, use_agent: bool = False) -> dict:
    """跑完整四角色流水线，返回结构化结果（含各阶段耗时）。"""
    t0 = time.time()
    # 1. 感知：意图 + 实体
    query = perceive(user_text)
    t1 = time.time()
    # 2. 图谱检索：疾病档案 / 多症状反查 / 鉴别诊断
    graph_data = graph_retrieve(query)
    t2 = time.time()
    # 3. 诊断：把检索结果作为事实交给大模型推理（不重复检索）
    diag = diagnose(user_text, retrieval=None if use_agent else graph_data)
    t3 = time.time()
    # 4. 报告
    report = generate_report(diag)
    t4 = time.time()

    result = {
        "input": user_text,
        "perception": query,
        "retrieval_hit": graph_data.get("hit", False),
        "retrieval": graph_data,
        "diagnosis": diag,
        "report": report,
        "timing": {
            "perception_s": round(t1 - t0, 2),
            "retrieval_s": round(t2 - t1, 2),
            "diagnosis_s": round(t3 - t2, 2),
            "report_s": round(t4 - t3, 2),
            "total_s": round(t4 - t0, 2),
        },
    }

    if verbose:
        print(f"输入: {user_text}")
        print(f"感知: {query}")
        print(f"检索命中: {graph_data.get('hit')} | 方式: {graph_data.get('mode')} | {graph_data.get('reason')}")
        print(f"诊断: {diag.get('root_cause')} | 置信度: {diag.get('confidence')}")
        print(f"耗时: {result['timing']}")
    return result


if __name__ == "__main__":
    demo = "我最近老是口渴、尿多，还瘦了，是不是糖尿病？"
    out = run_pipeline(demo, verbose=True)
    print("\n===== 报告 =====\n")
    print(out["report"])
