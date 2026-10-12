"""诊断 Agent 可调用的工具集合。

目前只有一个：疾病知识图谱检索工具 graph_search_tool。
返回精简 JSON，控制 token 消耗。
"""
import os
import sys
import json
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain.tools import tool

from agents.perception import perceive
from neo4j_tools.retriever import graph_retrieve


def _names(items, key: str = "name"):
    """从节点列表里取名字，兼容 dict / 字符串两种形态。"""
    out = []
    for it in items or []:
        if isinstance(it, dict):
            if it.get(key):
                out.append(it[key])
        elif it:
            out.append(str(it))
    return out


@tool(parse_docstring=False)
def graph_search_tool(user_text: str) -> str:
    """当用户描述症状、询问可能患的疾病、疾病的治疗方案/预防措施/就诊科室时调用本工具检索疾病知识图谱。

    输入：用户的原始问题文本。
    输出：检索到的图谱知识（JSON 字符串），或未命中的提示。
    """
    query = perceive(user_text)
    result = graph_retrieve(query)

    if not result.get("hit"):
        return json.dumps(
            {"hit": False, "intent": query.get("intent"), "msg": "疾病知识图谱未命中相关记录"},
            ensure_ascii=False,
        )

    disease = result.get("disease") or {}
    summary: Dict[str, Any] = {
        "hit": True,
        "intent": query.get("intent"),
        "matched_by": result.get("reason"),
        "why_top": result.get("why_top", ""),
        "disease": {
            "name": disease.get("name"),
            "alias": disease.get("alias1") or "",
            "type": disease.get("type"),
            "department": disease.get("department"),
            "description": disease.get("description"),
        },
        "symptoms": _names(result.get("symptoms")),
        "solutions": [
            {"name": s.get("name"), "steps": s.get("steps"), "cost": s.get("cost")}
            for s in result.get("solutions", []) if isinstance(s, dict)
        ],
        "preventions": [
            {"name": p.get("name"), "frequency": p.get("frequency"), "steps": p.get("steps")}
            for p in result.get("preventions", []) if isinstance(p, dict)
        ],
        "causes": [
            {"name": c.get("name"), "description": c.get("description")}
            for c in result.get("causes", []) if isinstance(c, dict)
        ],
    }

    # 多症状反查时，附上候选疾病与命中情况（含特异度加权分），供 Agent 排序推理
    if result.get("candidates"):
        summary["candidates"] = [
            {"name": c["name"], "hits": c["hits"], "coverage": c["coverage"],
             "score": c.get("score"), "matched_symptoms": c["matched_symptoms"]}
            for c in result["candidates"]
        ]

    # 鉴别诊断提示
    if result.get("differential"):
        summary["differential"] = [
            {"name": d.get("name"), "shared_symptoms": d.get("shared")}
            for d in result["differential"]
        ]

    return json.dumps(summary, ensure_ascii=False)
