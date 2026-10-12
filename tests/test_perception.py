"""感知层验收：意图识别 + 实体抽取（含规则兜底）。

运行：python tests/test_perception.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.perception import perceive, _rule_extract

CASES = [
    ("我最近老是口渴、尿多，还瘦了", "疾病诊断", "symptom"),
    ("消渴病平时要注意什么", "知识查询", "disease"),
    ("你好呀，你能做什么", "闲聊", None),
]

# 口语 → 规范名归一验收
NORMALIZE_CASES = [
    ("我最近老是口渴、尿多，还瘦了", {"多饮", "多尿", "体重下降"}),
    ("老是头疼头晕，心慌", {"头痛", "头晕", "心悸"}),
    ("发烧咳嗽，嗓子也疼", {"发热", "咳嗽", "咽痛"}),
]

PASS, FAIL = 0, 0

print("=" * 72)
print("感知层验收")
print("=" * 72)

for text, want_intent, want_key in CASES:
    out = perceive(text)
    ok_intent = out["intent"] == want_intent
    ok_entity = (want_key is None) or bool(out["entities"].get(want_key))
    ok_raw = out["raw"] == text
    print(f"\n输入：{text}")
    print(f"  输出：{json.dumps(out, ensure_ascii=False)}")
    print(f"  意图 {'OK' if ok_intent else 'FAIL'}（期望 {want_intent}，实际 {out['intent']}）"
          f" | 实体 {'OK' if ok_entity else 'FAIL'}"
          f" | raw {'OK' if ok_raw else 'FAIL'}")
    if ok_intent and ok_entity and ok_raw:
        PASS += 1
    else:
        FAIL += 1

print("\n" + "-" * 72)
print("口语症状归一（口渴→多饮、瘦了→体重下降、头疼→头痛）")
for text, expect in NORMALIZE_CASES:
    got = set(perceive(text)["entities"].get("symptom", []))
    ok = expect.issubset(got)
    print(f"  {'OK  ' if ok else 'FAIL'} {text}")
    print(f"       期望包含 {sorted(expect)} | 实际 {sorted(got)}")
    if ok:
        PASS += 1
    else:
        FAIL += 1

print("\n" + "-" * 72)
print("规则兜底（不调大模型，直接抽实体）")
r = _rule_extract("我头晕、心悸，是不是血压升高了")
print("  输入：我头晕、心悸，是不是血压升高了")
print(f"  输出：{json.dumps(r, ensure_ascii=False)}")
if "头晕" in r.get("symptom", []) and "心悸" in r.get("symptom", []):
    PASS += 1
    print("  [OK]   规则识别出 头晕 / 心悸")
else:
    FAIL += 1
    print("  [FAIL] 规则未识别出症状")

print(f"\n结果：通过 {PASS} 项，失败 {FAIL} 项")
sys.exit(0 if FAIL == 0 else 1)
