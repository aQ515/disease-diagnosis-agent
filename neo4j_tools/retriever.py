"""疾病知识图谱检索层。

对应《疾病诊断知识图谱设计》里的四个核心场景：
1. 疾病百科 —— 按标准病名 / 别名（常用名）检索疾病完整档案
2. 症状自查 —— 多症状 → 按命中数排序反查最可能的疾病（智能体主流程）
3. 鉴别诊断 —— 找出与命中疾病症状重叠的其他疾病，提醒注意区分
4. 症状关联 —— 单个症状能牵出哪些疾病

统一返回结构（便于上层 Agent 直接消费）：
{
    "hit": bool,                # 是否命中
    "reason": str,              # 未命中原因 / 命中方式说明
    "mode": str,                # disease / symptoms / text_fallback
    "disease": dict | None,     # 主命中疾病（含症状/方案/预防/病因/科室）
    "candidates": list,         # 多症状反查的候选疾病（按命中数排序）
    "symptoms": list,           # 症状名列表
    "solutions": list,          # 治疗方案
    "preventions": list,        # 预防措施
    "causes": list,             # 病因
    "department": dict | None,  # 推荐科室
    "differential": list,       # 鉴别诊断：症状重叠的其他疾病
    "raw_paths": list,
}
"""
from typing import Dict, Any, List

from .connection import get_graph

DOMAIN = "disease"
MAX_CANDIDATES = 3          # 多症状反查最多返回几个候选疾病

# 症状词表兜底：图谱未加载时也能让规则抽取工作
_FALLBACK_SYMPTOMS = [
    "多饮", "多尿", "体重下降", "乏力", "头晕", "头痛", "心悸",
    "发热", "咳嗽", "咽痛",
]


def _empty_result(reason: str = "未命中图谱") -> Dict[str, Any]:
    """检索不到数据时统一返回空结构，避免上层到处判 None。"""
    return {
        "hit": False,
        "reason": reason,
        "mode": "none",
        "disease": None,
        "candidates": [],
        "why_top": "",
        "symptoms": [],
        "solutions": [],
        "preventions": [],
        "causes": [],
        "department": None,
        "differential": [],
        "evidence": [],
        "raw_paths": [],
    }


def _node_dict(node) -> dict:
    """py2neo Node 转普通字典（None 直接透传）。"""
    return dict(node) if node is not None else None


# ---------------------------------------------------------------- 词表


def list_symptom_names() -> List[str]:
    """从图谱读出全部症状名，供感知层的规则兜底使用。"""
    try:
        rows = get_graph().run(
            f"MATCH (s:Symptom {{domain:'{DOMAIN}'}}) RETURN s.name AS name"
        ).data()
        names = [r["name"] for r in rows if r["name"]]
        return names or _FALLBACK_SYMPTOMS
    except Exception:
        return _FALLBACK_SYMPTOMS


def list_disease_names() -> List[dict]:
    """读出全部疾病及其别名，供感知层做名称/别名匹配。"""
    try:
        return get_graph().run(
            f"""MATCH (d:Disease {{domain:'{DOMAIN}'}})
                RETURN d.name AS name, d.alias1 AS alias1, d.alias2 AS alias2"""
        ).data()
    except Exception:
        return []


# ---------------------------------------------------------------- 疾病档案


def _retrieve_by_disease(graph, name: str) -> Dict[str, Any]:
    """按病名或别名检索疾病档案（别名匹配是重点，如「消渴病」→ 2型糖尿病）。"""
    sql = """
MATCH (d:Disease {domain:'disease'})
// 精确匹配标准名/别名优先，其次是双向包含（处理「我得了高血压病」这类口语）
WHERE d.name = $text OR d.alias1 = $text OR d.alias2 = $text
   OR $text CONTAINS d.name OR $text CONTAINS d.alias1 OR $text CONTAINS d.alias2
   OR d.name CONTAINS $text OR d.alias1 CONTAINS $text OR d.alias2 CONTAINS $text
WITH d,
     CASE WHEN d.name = $text OR d.alias1 = $text OR d.alias2 = $text
          THEN 0 ELSE 1 END AS rank
ORDER BY rank
LIMIT 1
OPTIONAL MATCH (d)-[:HAS_SYMPTOM]->(s:Symptom)
OPTIONAL MATCH (d)-[:TREATED_BY]->(sol:Solution)
OPTIONAL MATCH (d)-[:PREVENTED_BY]->(p:Prevention)
OPTIONAL MATCH (d)-[:CAUSED_BY]->(c:Cause)
OPTIONAL MATCH (d)-[:BELONGS_TO]->(dep:Department)
RETURN d,
       collect(DISTINCT s)   AS symptoms,
       collect(DISTINCT sol) AS solutions,
       collect(DISTINCT p)   AS preventions,
       collect(DISTINCT c)   AS causes,
       collect(DISTINCT dep) AS departments
    """
    rows = graph.run(sql, text=name).data()
    if not rows or not rows[0]["d"]:
        return _empty_result(f"未找到疾病: {name}")

    r = rows[0]
    d = _node_dict(r["d"])
    if not d:
        return _empty_result(f"未找到疾病: {name}")

    deps = [_node_dict(x) for x in r["departments"] if x]
    result = {
        "hit": True,
        "reason": f"按名称/别名命中：{d.get('name')}",
        "mode": "disease",
        "disease": d,
        "candidates": [],
        "why_top": f"用户输入与疾病标准名/常用名匹配（{d.get('name')}）",
        "symptoms": [x["name"] for x in (_node_dict(i) for i in r["symptoms"]) if x],
        "solutions": [_node_dict(x) for x in r["solutions"] if x],
        "preventions": [_node_dict(x) for x in r["preventions"] if x],
        "causes": [_node_dict(x) for x in r["causes"] if x],
        "department": deps[0] if deps else None,
        "differential": _differential(graph, d["name"]),
        "evidence": evidence_paths(graph, d["name"]),
        "raw_paths": [],
    }
    return result


def _differential(graph, disease_name: str) -> List[dict]:
    """鉴别诊断：找出症状与该疾病重叠的其他疾病，按重叠数降序。"""
    sql = """
MATCH (d:Disease {name:$name})-[:HAS_SYMPTOM]->(s:Symptom)<-[:HAS_SYMPTOM]-(o:Disease)
WHERE o <> d
RETURN o.name AS name, o.alias1 AS alias1, collect(DISTINCT s.name) AS shared
ORDER BY size(shared) DESC
LIMIT 3
    """
    try:
        return graph.run(sql, name=disease_name).data()
    except Exception:
        return []


# ---------------------------------------------------------------- 创新点：证据链


def evidence_paths(graph, disease_name: str, limit: int = 20) -> List[dict]:
    """把该疾病在图谱里真实走过的边取出来，作为报告的「证据链」。

    这是图数据库相对向量检索的关键优势：结论可回溯到具体的边，
    而不是一句「根据相关资料」。
    """
    sql = """
MATCH (d:Disease {name:$name})-[r]->(n)
RETURN d.name AS disease, type(r) AS rel, n.name AS target, labels(n)[0] AS target_label
ORDER BY rel, target
LIMIT $limit
    """
    try:
        return graph.run(sql, name=disease_name, limit=limit).data()
    except Exception:
        return []


def graph_subgraph(graph, disease_name: str, limit: int = 40) -> Dict[str, Any]:
    """取该疾病的一跳子图（节点 + 边），供前端画图。

    Cytoscape/vis 之类的库体积大，这里返回结构化数据由前端自己画 SVG。
    """
    sql = """
MATCH (d:Disease {name:$name})
OPTIONAL MATCH (d)-[r]->(n)
RETURN d, collect({rel: type(r), node: n, label: labels(n)[0]}) AS edges
    """
    try:
        rows = graph.run(sql, name=disease_name).data()
    except Exception:
        return {"nodes": [], "links": []}
    if not rows:
        return {"nodes": [], "links": []}

    d = _node_dict(rows[0]["d"]) or {}
    nodes = [{"id": d.get("name"), "label": d.get("name"), "group": "Disease",
              "alias": d.get("alias1") or "", "desc": d.get("description", "")}]
    links = []
    seen = {d.get("name")}
    for e in rows[0]["edges"][:limit]:
        n = _node_dict(e.get("node"))
        if not n or not n.get("name"):
            continue
        if n["name"] not in seen:
            seen.add(n["name"])
            nodes.append({"id": n["name"], "label": n["name"],
                          "group": e.get("label") or "Other",
                          "desc": n.get("description", "")})
        links.append({"source": d.get("name"), "target": n["name"], "rel": e.get("rel")})
    return {"nodes": nodes, "links": links}



# ---------------------------------------------------------------- 多症状反查


def _symptom_degrees(graph, symptoms: List[str]) -> Dict[str, int]:
    """每个症状能指示多少种疾病 —— 用来算「症状特异度」。

    「多饮」只指向糖尿病（deg=1，很特异），「乏力」指向 3 个病（deg=3，很不特异）。
    同样命中一个症状，前者的诊断价值远高于后者。
    """
    sql = """
UNWIND $symptoms AS sn
MATCH (s:Symptom {name: sn})-[:INDICATES]->(:Disease)
RETURN s.name AS name, count(*) AS deg
    """
    try:
        rows = graph.run(sql, symptoms=list(symptoms)).data()
        return {r["name"]: max(int(r["deg"]), 1) for r in rows}
    except Exception:
        return {}


def _retrieve_by_symptoms(graph, symptoms: List[str]) -> Dict[str, Any]:
    """多症状反查疾病：按命中数排序，并给出症状重叠的鉴别提示。

    创新点：排序不只看「命中几个」，而是用**特异度加权分**——
    score = Σ(1 / 该症状可指示的疾病数)，命中「多饮」比命中「乏力」得分高得多。
    """
    sql = """
UNWIND $symptoms AS sn
MATCH (s:Symptom {name: sn})-[:INDICATES]->(d:Disease)
WITH d, count(DISTINCT s) AS hits, collect(DISTINCT s.name) AS matched
ORDER BY hits DESC, d.name
LIMIT $limit
OPTIONAL MATCH (d)-[:TREATED_BY]->(sol:Solution)
OPTIONAL MATCH (d)-[:BELONGS_TO]->(dep:Department)
RETURN d, hits, matched,
       collect(DISTINCT sol) AS solutions,
       collect(DISTINCT dep) AS departments
    """
    rows = graph.run(sql, symptoms=list(symptoms), limit=MAX_CANDIDATES).data()
    if not rows:
        return _empty_result(f"症状未命中图谱: {symptoms}")

    # 特异度加权
    degrees = _symptom_degrees(graph, symptoms)
    max_score = sum(1.0 / degrees.get(s, 1) for s in symptoms) or 1.0

    candidates = []
    for r in rows:
        d = _node_dict(r["d"]) or {}
        deps = [_node_dict(x) for x in r["departments"] if x]
        matched = r["matched"] or []
        score = sum(1.0 / degrees.get(s, 1) for s in matched)
        candidates.append({
            "name": d.get("name"),
            "alias1": d.get("alias1", ""),
            "type": d.get("type", ""),
            "department": deps[0]["name"] if deps else d.get("department", ""),
            "description": d.get("description", ""),
            "hits": r["hits"],
            "coverage": round(r["hits"] / max(len(symptoms), 1), 3),
            # 特异度加权分（0~1），越接近 1 说明命中的都是「指向性很强」的症状
            "score": round(score / max_score, 3),
            "matched_symptoms": matched,
            # 未命中的症状：作为追问素材
            "missed_symptoms": [s for s in symptoms if s not in matched],
            "solutions": [x["name"] for x in (_node_dict(i) for i in r["solutions"]) if x],
        })

    # 排序：加权分优先，其次命中数
    candidates.sort(key=lambda c: (c["score"], c["hits"]), reverse=True)
    top = candidates[0]

    # 为什么它排第一 —— 前端直接展示，避免"黑盒排序"
    why = (f"命中 {top['hits']}/{len(symptoms)} 个症状（覆盖度 {top['coverage']:.0%}），"
           f"其中 {'、'.join(top['matched_symptoms'])} 指向性较强，"
           f"综合特异度加权分 {top['score']:.2f}")

    result = {
        "hit": True,
        "reason": f"按 {len(symptoms)} 个症状反查，最高命中 {top['hits']} 个",
        "mode": "symptoms",
        "disease": {
            "name": top["name"],
            "alias1": top.get("alias1", ""),
            "type": top.get("type", ""),
            "department": top.get("department", ""),
            "description": top.get("description", ""),
        },
        "candidates": candidates,
        "why_top": why,
        "symptoms": list(symptoms),
        "solutions": [{"name": n} for n in top["solutions"]],
        "preventions": _preventions_of(graph, top["name"]),
        "causes": _causes_of(graph, top["name"]),
        "department": {"name": top.get("department", "")} if top.get("department") else None,
        "differential": _differential(graph, top["name"]),
        "evidence": evidence_paths(graph, top["name"]),
        "raw_paths": [],
    }
    return result


def _preventions_of(graph, disease_name: str) -> List[dict]:
    """补取预防措施（多症状反查时按需补查，避免主查询过大）。"""
    try:
        return [
            _node_dict(x)
            for x in graph.run(
                "MATCH (d:Disease {name:$name})-[:PREVENTED_BY]->(p:Prevention) RETURN p",
                name=disease_name,
            ).data()
            for x in [x["p"]]
            if x
        ]
    except Exception:
        return []


def _causes_of(graph, disease_name: str) -> List[dict]:
    """补取病因。"""
    try:
        return [
            _node_dict(x)
            for x in graph.run(
                "MATCH (d:Disease {name:$name})-[:CAUSED_BY]->(c:Cause) RETURN c",
                name=disease_name,
            ).data()
            for x in [x["c"]]
            if x
        ]
    except Exception:
        return []


# ---------------------------------------------------------------- 文本兜底


def _retrieve_by_text(graph, text: str) -> Dict[str, Any]:
    """兜底：先从原文里认病名/别名，认不出再认症状词。"""
    profile = _retrieve_by_disease(graph, text)
    if profile["hit"]:
        return profile

    hit_symptoms = [s for s in list_symptom_names() if s in text]
    if hit_symptoms:
        return _retrieve_by_symptoms(graph, hit_symptoms)

    return _empty_result(f"文本未命中疾病或症状: {text}")


# ---------------------------------------------------------------- 入口


def graph_retrieve(query: Dict[str, Any]) -> Dict[str, Any]:
    """图谱检索入口。

    优先级：疾病实体 > 症状实体（多症状反查）> 原文兜底。
    query 可以是感知层产出的 dict，也可以直接传一段字符串。
    """
    if isinstance(query, str):
        return _retrieve_by_text(get_graph(), query)

    entities = query.get("entities", {}) or {}
    raw = query.get("raw", "")
    graph = get_graph()

    # 1. 明确说到某个病（含别名）
    disease = entities.get("disease")
    if disease:
        result = _retrieve_by_disease(graph, disease)
        if result["hit"]:
            return result

    # 2. 描述了一组症状 → 主流程：反查疾病
    symptoms = entities.get("symptom") or []
    if isinstance(symptoms, str):
        symptoms = [symptoms]
    if symptoms:
        result = _retrieve_by_symptoms(graph, symptoms)
        if result["hit"]:
            return result

    # 3. 兜底
    if raw:
        return _retrieve_by_text(graph, raw)
    return _empty_result("未提供可检索实体")


# ---------------------------------------------------------------- 对外便捷接口


def get_subgraph(disease_name: str) -> Dict[str, Any]:
    """取某疾病的一跳子图（供前端可视化）。"""
    return graph_subgraph(get_graph(), disease_name)


def get_evidence(disease_name: str) -> List[dict]:
    """取某疾病的图谱证据链。"""
    return evidence_paths(get_graph(), disease_name)


def get_disease_profile(name: str) -> Dict[str, Any]:
    """按病名/别名取完整档案（别名检索走这里）。"""
    return _retrieve_by_disease(get_graph(), name)
