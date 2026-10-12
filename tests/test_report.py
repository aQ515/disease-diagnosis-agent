"""报告护栏验收：模型编出来的剂量必须被拦掉。

不依赖大模型，直接测 guard_dosage。
运行：python tests/test_report.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.report import guard_dosage

# 诊断结论里只有这些事实（图谱数据）
SOURCE = {
    "root_cause": "2型糖尿病",
    "solutions": [{"name": "二甲双胍口服", "steps": "从小剂量起始随餐服用，逐步加量并定期复查肾功能"}],
    "preventions": [
        {"name": "限制钠盐摄入", "steps": "每日食盐摄入控制在5克以下"},
        {"name": "规律有氧运动", "steps": "每周5次"},
    ],
}

CASES = [
    # (说明, 报告文本, 期望包含, 期望不包含)
    ("编造剂量应被替换（含区间写法）",
     "建议服用二甲双胍，起始剂量通常为500mg每日1-2次，随餐服用。",
     ["具体用量请遵医嘱"], ["500mg", "1-2次"]),
    ("图谱已有的数字应保留",
     "饮食上每日食盐摄入控制在5克以下。",
     ["5克"], ["具体用量请遵医嘱"]),
    ("图谱里已有的运动频次应保留",
     "每周至少150分钟中等强度运动，每周5次。",
     ["每周5次"], ["具体用量请遵医嘱"]),
    ("纯生活方式建议不受影响",
     "建议每日中等强度运动30分钟，控制总热量摄入。",
     ["30分钟"], ["具体用量请遵医嘱"]),
]

PASS, FAIL = 0, 0
print("=" * 72)
print("报告剂量护栏验收")
print("=" * 72)

for title, text, must_have, must_not in CASES:
    out = guard_dosage(text, SOURCE)
    ok = all(k in out for k in must_have) and all(k not in out for k in must_not)
    print(f"\n{'[OK]  ' if ok else '[FAIL]'} {title}")
    print(f"  输入: {text}")
    print(f"  输出: {out}")
    if ok:
        PASS += 1
    else:
        FAIL += 1

print(f"\n结果：通过 {PASS} 项，失败 {FAIL} 项")
sys.exit(0 if FAIL == 0 else 1)
