"""验收后端接口（在 VM 上跑）：retrieve / subgraph / diagnose。"""
import json
import urllib.request

BASE = "http://127.0.0.1:8001/api"


def post(path, payload, timeout=180):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def get(path, timeout=60):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.load(r)


print("=" * 72)
print("[1] POST /api/retrieve/  只查图谱")
d = post("/retrieve/", {"text": "我最近老是口渴、尿多，还瘦了"})
print("  感知:", d["perception"]["intent"], d["perception"]["entities"])
r = d["retrieval"]
print("  命中:", d["retrieval_hit"], "| 方式:", r["mode"], "|", r["reason"])
print("  为什么排第一:", r.get("why_top"))
for c in r.get("candidates", []):
    print("   - %s: hits=%s coverage=%s score=%s 命中=%s"
          % (c["name"], c["hits"], c["coverage"], c["score"], c["matched_symptoms"]))
print("  鉴别诊断:", [(x["name"], x.get("shared")) for x in r.get("differential", [])])
print("  证据链条数:", len(r.get("evidence", [])))

print("=" * 72)
print("[2] GET /api/graph/subgraph/  子图可视化数据")
g = get("/graph/subgraph/?name=2%E5%9E%8B%E7%B3%96%E5%B0%BF%E7%97%85")
print("  节点 %d 个 / 边 %d 条" % (len(g["nodes"]), len(g["links"])))
print("  节点组:", sorted({n["group"] for n in g["nodes"]}))
print("  关系类型:", sorted({l["rel"] for l in g["links"]}))

print("=" * 72)
print("[3] POST /api/diagnose/  完整流水线（含报告）")
d3 = post("/diagnose/", {"text": "消渴病患者平时应该注意什么？"})
print("  命中疾病:", (d3["retrieval"].get("disease") or {}).get("name"))
print("  诊断:", d3["diagnosis"].get("root_cause"), "| 置信度:", d3["diagnosis"].get("confidence"))
print("  报告字数:", len(d3["report"]))
print("  报告前 160 字:", d3["report"][:160].replace("\n", " "))
print("  耗时:", d3["timing"])
