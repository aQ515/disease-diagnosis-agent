"""端到端验收：两个典型场景跑完整四角色流水线。

场景 A：症状自查（多症状 → 反查疾病）
场景 B：疾病百科（别名 → 疾病档案）

需要 Neo4j + DASHSCOPE_API_KEY（会真实调用大模型）。
运行：python tests/test_pipeline.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.pipeline import run_pipeline

SCENARIOS = [
    ("场景A 症状自查", "我最近老是口渴、尿多，还瘦了，是不是糖尿病？", "2型糖尿病"),
    ("场景B 疾病百科", "消渴病患者平时应该注意什么？", "2型糖尿病"),
]

PASS, FAIL = 0, 0

print("=" * 72)
print("端到端验收：四角色流水线")
print("=" * 72)

for title, text, expect_name in SCENARIOS:
    print(f"\n{'=' * 72}\n{title}：{text}\n{'=' * 72}")
    out = run_pipeline(text, verbose=True)

    hit = out["retrieval_hit"]
    got = (out["retrieval"].get("disease") or {}).get("name")
    diag = out["diagnosis"]
    has_report = bool(out["report"]) and len(out["report"]) > 50

    ok = hit and got == expect_name and has_report
    print(f"\n  检索命中: {'OK' if hit else 'FAIL'}")
    print(f"  命中疾病: {'OK' if got == expect_name else 'FAIL'}（期望 {expect_name}，实际 {got}）")
    print(f"  诊断结论: {diag.get('root_cause')} | 置信度: {diag.get('confidence')}")
    print(f"  报告生成: {'OK' if has_report else 'FAIL'}（{len(out['report'])} 字）")
    print(f"  耗时: {out['timing']}")
    print("\n  -------- 报告原文 --------")
    print("  " + out["report"].replace("\n", "\n  "))

    if ok:
        PASS += 1
    else:
        FAIL += 1

print(f"\n{'=' * 72}")
print(f"结果：通过 {PASS} 个场景，失败 {FAIL} 个")
sys.exit(0 if FAIL == 0 else 1)
