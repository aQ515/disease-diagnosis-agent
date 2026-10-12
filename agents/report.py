"""报告角色：把诊断结论整理成给用户看的自然语言报告。

报告固定三块：诊断结论 / 处理建议 / 风险提示。
闲聊等非诊断场景不套模板，直接返回模型输出。

安全护栏：医疗场景最怕模型"编剂量"。报告生成后会过一遍剂量校验，
凡是图谱原文里没有的剂量数字（如「500mg 每日2次」）一律替换为「具体用量请遵医嘱」。
"""
import os
import re
import sys
import json
from typing import Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.llm import get_llm

REPORT_PROMPT = """把下面的疾病辅助诊断结论整理成一份简洁的中文报告，固定包含三部分：

1. 诊断结论：主要考虑什么病（带上常用名）、判断依据、置信度
2. 处理建议：治疗方案（分点说明步骤）、需要就诊的科室
3. 风险提示：需要警惕什么、什么情况必须立即就医、与哪些疾病需要鉴别

严格约束（重要）：
- 只使用诊断结论里已有的信息，绝对不要新增疾病、药物名称
- **绝不允许写出任何具体剂量、用法用量数字**（如 500mg、每日2次、每次1片）；需要提及用药时只写「遵医嘱」
- 语气客观平实，面向普通用户，不要夸大
- 最后一行原样附上免责声明

诊断结论(JSON)：
{diagnosis}

报告："""

# 剂量类描述：500mg、0.25g、1片、10ml、每日2次、1-2次、每次5毫克 等
# 数字部分支持区间写法（1-2、1~2、1至2）
_NUM = r"\d+(?:\.\d+)?(?:\s*[-~至]\s*\d+(?:\.\d+)?)?"
DOSAGE_RE = re.compile(
    rf"{_NUM}\s*(?:mg|毫克|g|克|μg|微克|ml|毫升|片|粒|IU|单位|次)"
    rf"(?:\s*[/每]\s*(?:日|天|次))?"
    rf"|每\s*日\s*{_NUM}\s*次"
    rf"|每\s*次\s*{_NUM}\s*(?:mg|毫克|g|克|片|粒|ml|毫升)"
)
SAFE_REPLACEMENT = "具体用量请遵医嘱"


def guard_dosage(report: str, source: Dict) -> str:
    """把模型编出来的剂量替换掉：只保留图谱原文里确实出现过的数字描述。"""
    source_text = json.dumps(source, ensure_ascii=False)
    replaced = []

    def _sub(m):
        text = m.group(0)
        # 图谱里本来就有（如「每日食盐摄入控制在5克以下」）→ 保留
        if text in source_text:
            return text
        replaced.append(text)
        return SAFE_REPLACEMENT

    out = DOSAGE_RE.sub(_sub, report)
    if replaced:
        out += f"\n\n（注：报告中 {len(replaced)} 处具体用量未见于知识图谱，已替换为「{SAFE_REPLACEMENT}」。）"
    return out


def generate_report(diagnosis: Dict) -> str:
    """生成可读报告（含剂量护栏）。"""
    llm = get_llm()
    payload = json.dumps(diagnosis, ensure_ascii=False)
    raw = llm.predict(REPORT_PROMPT.format(diagnosis=payload))
    return guard_dosage(raw, diagnosis)


def full_pipeline(user_text: str) -> str:
    """便捷入口：一句话跑完诊断 + 报告。"""
    from agents.diagnosis_agent import diagnose

    return generate_report(diagnose(user_text))
