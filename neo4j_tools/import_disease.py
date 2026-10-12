"""一键导入疾病诊断知识图谱 CSV。

运行:  python -m neo4j_tools.import_disease

与原设备图谱共存的做法：所有疾病图谱节点统一打上 domain="disease" 标记，
清库时只删带该标记的节点，不会误删原有的 Equipment / Fault 数据。
"""
import sys
import os
import csv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from py2neo import Graph

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

DOMAIN = "disease"
NODE_LABELS = ["Disease", "Symptom", "Solution", "Prevention", "Cause", "Department"]

REL_MAP = {
    "HAS_SYMPTOM": ("Disease", "Symptom"),
    "TREATED_BY": ("Disease", "Solution"),
    "PREVENTED_BY": ("Disease", "Prevention"),
    "CAUSED_BY": ("Disease", "Cause"),
    "BELONGS_TO": ("Disease", "Department"),
    "INDICATES": ("Symptom", "Disease"),
}


def _ensure_unique_constraint(graph, label: str) -> None:
    """建立 name 唯一约束，兼容 Neo4j 3.5(ON..ASSERT) 与 4.x/5.x(FOR..REQUIRE) 两种语法。"""
    name = f"{label.lower()}_name"
    for stmt in (
        f"CREATE CONSTRAINT {name} IF NOT EXISTS FOR (n:{label}) REQUIRE n.name IS UNIQUE",
        f"CREATE CONSTRAINT ON (n:{label}) ASSERT n.name IS UNIQUE",
    ):
        try:
            graph.run(stmt)
            return
        except Exception:
            continue


def import_all(clear: bool = True) -> None:
    graph = Graph(config.NEO4J_URI, auth=(config.NEO4J_USER, config.NEO4J_PASSWORD))

    if clear:
        graph.run("MATCH (n {domain: $d}) DETACH DELETE n", d=DOMAIN)
        print(f"[1/4] 已清空旧的疾病图谱数据（domain={DOMAIN}）")

    for label in NODE_LABELS:
        _ensure_unique_constraint(graph, label)
    print("[2/4] 约束已就绪")

    with open(os.path.join(DATA_DIR, "disease_entities.csv"), encoding="utf-8-sig") as f:
        entities = list(csv.DictReader(f))

    for e in entities:
        label = e["label"]
        props = {str(k): v for k, v in e.items() if k not in ("label", "name") and v}
        props["domain"] = DOMAIN
        cypher = f"MERGE (n:{label} {{name: $name}}) SET n += $props"
        graph.run(cypher, name=e["name"], props=props)
    print(f"[3/4] 已导入 {len(entities)} 个节点")

    with open(os.path.join(DATA_DIR, "disease_relations.csv"), encoding="utf-8-sig") as f:
        relations = list(csv.DictReader(f))

    cnt = 0
    skipped = []
    for r in relations:
        pair = REL_MAP.get(r["rel_type"])
        if not pair:
            skipped.append(r["rel_type"])
            continue
        from_l, to_l = pair
        cypher = (
            f"MATCH (a:{from_l} {{name: $from_name}}), (b:{to_l} {{name: $to_name}}) "
            f"MERGE (a)-[:{r['rel_type']}]->(b)"
        )
        graph.run(cypher, from_name=r["from_name"], to_name=r["to_name"])
        cnt += 1
    print(f"[4/4] 已导入 {cnt} 条关系" + (f"（跳过未知类型: {set(skipped)}）" if skipped else ""))

    n = graph.run("MATCH (n {domain: $d}) RETURN count(n) AS c", d=DOMAIN).data()[0]["c"]
    r2 = graph.run(
        "MATCH (a {domain: $d})-[r]->(b {domain: $d}) RETURN count(r) AS c", d=DOMAIN
    ).data()[0]["c"]
    print(f"\n导入完成: 疾病图谱节点 {n} 个, 关系 {r2} 条")

    print("\n--- 各标签节点数 ---")
    for label in NODE_LABELS:
        c = graph.run(
            f"MATCH (n:{label} {{domain: $d}}) RETURN count(n) AS c", d=DOMAIN
        ).data()[0]["c"]
        print(f"  {label}: {c}")


if __name__ == "__main__":
    import_all()
