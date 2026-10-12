"""检索层验收：别名检索 / 疾病档案 / 多症状反查 / 共享症状鉴别。

只依赖 Neo4j，不调用大模型，可离线反复跑。
运行：python tests/test_retriever.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from neo4j_tools.retriever import graph_retrieve

PASS, FAIL = 0, 0


def check(title: str, ok: bool, detail: str = ""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [OK]   {title}" + (f" —— {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  [FAIL] {title}" + (f" —— {detail}" if detail else ""))


def line():
    print("-" * 72)


print("=" * 72)
print("检索层验收（疾病知识图谱，31 节点 / 42 关系）")
print("=" * 72)

# ---------- 1. 别名检索：用常用名「消渴病」找到 2 型糖尿病 ----------
line()
print("1. 别名检索：说「消渴病」应命中 2型糖尿病")
r = graph_retrieve("消渴病平时要注意什么")
check("命中", r["hit"], r["reason"])
check("疾病 = 2型糖尿病", (r.get("disease") or {}).get("name") == "2型糖尿病",
      f"实际: {(r.get('disease') or {}).get('name')}")
check("带出症状 4 个", len(r["symptoms"]) == 4, f"实际: {r['symptoms']}")
check("带出治疗方案", len(r["solutions"]) >= 1, f"实际: {len(r['solutions'])} 个")
check("带出预防措施", len(r["preventions"]) >= 1, f"实际: {len(r['preventions'])} 个")
check("推荐科室 = 内分泌科", (r.get("department") or {}).get("name") == "内分泌科",
      f"实际: {(r.get('department') or {}).get('name')}")

# ---------- 2. 另一个别名：血压升高 → 原发性高血压 ----------
line()
print("2. 别名检索：说「血压升高」应命中 原发性高血压")
r2 = graph_retrieve("血压升高要注意什么")
check("疾病 = 原发性高血压", (r2.get("disease") or {}).get("name") == "原发性高血压",
      f"实际: {(r2.get('disease') or {}).get('name')}")

# ---------- 3. 多症状反查（主流程）----------
line()
print("3. 多症状反查：「口渴、尿多、瘦了」应首选 2型糖尿病")
r3 = graph_retrieve({"entities": {"symptom": ["多饮", "多尿", "体重下降"]}, "raw": ""})
check("命中", r3["hit"], r3["reason"])
check("mode = symptoms", r3["mode"] == "symptoms", r3["mode"])
top = (r3.get("disease") or {}).get("name")
check("首选 2型糖尿病", top == "2型糖尿病", f"实际: {top}")
if r3.get("candidates"):
    c0 = r3["candidates"][0]
    check("排序第一命中 3 个症状", c0["hits"] == 3, f"hits={c0['hits']}, coverage={c0['coverage']}")

# ---------- 4. 共享症状 → 鉴别诊断（乏力同时属于 3 个病）----------
line()
print("4. 共享症状鉴别：查询 2型糖尿病 应提示「乏力」重叠的其他疾病")
r4 = graph_retrieve("2型糖尿病")
diff = r4.get("differential") or []
check("给出鉴别疾病", len(diff) >= 1, f"实际: {[d.get('name') for d in diff]}")
shared_flat = [s for d in diff for s in (d.get("shared") or [])]
check("鉴别依据含共享症状「乏力」", "乏力" in shared_flat, f"shared={sorted(set(shared_flat))}")

# ---------- 5. 单症状 → 多个疾病 ----------
line()
print("5. 症状关联多疾病：「发热」应牵出 流行性感冒")
r5 = graph_retrieve({"entities": {"symptom": ["发热"]}, "raw": ""})
names = [c["name"] for c in r5.get("candidates", [])]
check("命中", r5["hit"], r5["reason"])
check("候选含 流行性感冒", "流行性感冒" in names, f"实际: {names}")

# ---------- 6. 未命中兜底 ----------
line()
print("6. 边界：与医疗无关的输入应返回未命中而不报错")
r6 = graph_retrieve({"entities": {}, "raw": "今天天气不错"})
check("不报错", isinstance(r6, dict))
check("hit=False", r6["hit"] is False, r6["reason"])

line()
print(f"结果：通过 {PASS} 项，失败 {FAIL} 项")
sys.exit(0 if FAIL == 0 else 1)
