"""环境自检：Neo4j 连接 + 图谱规模 + 大模型连通。

运行：python tests/test_env.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import config
from neo4j_tools.connection import get_graph

print("=" * 72)
print("环境自检")
print("=" * 72)

# 1) Neo4j
print(f"\n[1] Neo4j: {config.NEO4J_URI}  用户: {config.NEO4J_USER}")
try:
    graph = get_graph()
    print("    连接 OK:", graph.run("RETURN 'hello neo4j' AS msg").data())
    n = graph.run("MATCH (n {domain:'disease'}) RETURN count(n) AS c").data()[0]["c"]
    r = graph.run(
        "MATCH (a {domain:'disease'})-[x]->(b {domain:'disease'}) RETURN count(x) AS c"
    ).data()[0]["c"]
    print(f"    疾病图谱规模: 节点 {n} 个, 关系 {r} 条")
    print("\n    各标签节点数：")
    for label in ["Disease", "Symptom", "Solution", "Prevention", "Cause", "Department"]:
        c = graph.run(f"MATCH (n:{label} {{domain:'disease'}}) RETURN count(n) AS c").data()[0]["c"]
        print(f"      {label:<11} {c}")
    other = graph.run("MATCH (n) WHERE n.domain IS NULL RETURN count(n) AS c").data()[0]["c"]
    print(f"    （库内其它来源节点 {other} 个，不受影响）")
except Exception as e:
    print("    连接失败:", e)

# 2) 大模型
print(f"\n[2] 大模型: {config.QWEN_MODEL_NAME}")
try:
    from agents.llm import get_llm

    llm = get_llm(temperature=0.0)
    print("    调用 OK:", llm.invoke("用一句话说明什么是疾病知识图谱").content[:80], "...")
except Exception as e:
    print("    调用失败:", e)
