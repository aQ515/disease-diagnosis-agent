"""幻觉检测：判断回答里是否出现了知识图谱之外的药物 / 疾病名称。

为什么要单独做这个：大模型在医疗问答里最危险的错误是「编药」——
推荐一个知识库里根本没有的药，或者编一个不存在的病。
本项目用「图谱白名单」作为判据来量化这件事。

抽取方式两种：
1. 首选：小模型抽取（只输出标准药物名/疾病名，避免把句子片段当实体）
2. 兜底：规则抽取（正则 + 停用字过滤），大模型不可用时仍能出结果
"""
import re
from typing import Dict, List

# ---------------- 规则抽取（兜底） ----------------

DRUG_SUFFIX = (
    "片", "胶囊", "颗粒", "口服液", "注射液", "注射剂", "软膏", "乳膏",
    "滴剂", "滴眼液", "喷雾剂", "气雾剂", "栓", "丸", "散", "糖浆", "贴",
)
DISEASE_SUFFIX = (
    "病", "炎", "症", "综合征", "感染", "衰竭", "硬化", "结石", "溃疡",
    "梗死", "肿瘤", "癌", "瘤", "中毒", "损伤",
)

# 出现这些字基本说明匹配到的是句子片段而不是实体名（如「型糖尿病的典型警示症」）
BAD_CHARS = set(
    "的得了是与和或及等会可需要常见很更最已将能应该不没无为于在从向对把被让使因所以而且但并"
    "个项种类些实初终如若则因其此该各每所有无具有包括例如比如同时此外另外"
)

# 词本身是后缀组合但不是实体（否则会大量误报）
STOPWORDS = {
    "并发症", "合并症", "继发症", "后遗症", "禁忌症", "适应症", "症状", "综合症",
    "炎症", "癌症", "炎症反应", "慢性病", "急性病", "基础病", "原发病", "风险",
    "不良反应", "副作用", "处方", "药片", "药物", "药品", "治疗", "诊断",
    "可能疾病", "其他疾病", "其他可能疾病", "上述疾病", "该类疾病", "相关疾病",
}

_CJK = r"\u4e00-\u9fa5"
DRUG_RE = re.compile(rf"([{_CJK}]{{2,6}}(?:{'|'.join(DRUG_SUFFIX)}))")
DISEASE_RE = re.compile(rf"([{_CJK}]{{2,8}}(?:{'|'.join(DISEASE_SUFFIX)}))")


def _plausible(term: str) -> bool:
    """过滤明显不是实体名的匹配结果。"""
    if not term or term in STOPWORDS:
        return False
    if any(ch in BAD_CHARS for ch in term):
        return False
    # 全是同一字的重复（如「炎炎」）
    if len(set(term)) == 1:
        return False
    return True


def _dedupe(seq: List[str]) -> List[str]:
    out, seen = [], set()
    for s in seq:
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def extract_by_rules(text: str) -> Dict[str, List[str]]:
    """规则抽取：中文名 + 剂型/疾病后缀，再做停用字过滤。"""
    text = text or ""
    drugs = [m for m in DRUG_RE.findall(text) if _plausible(m)]
    diseases = [m for m in DISEASE_RE.findall(text) if _plausible(m)]
    return {"drugs": _dedupe(drugs), "diseases": _dedupe(diseases)}


# ---------------- 大模型抽取（首选） ----------------

EXTRACT_PROMPT = """从下面这段医疗回答里，抽出它提到的**药物名称**和**疾病名称**。

要求：
- 只输出标准名称，不要输出句子片段（错误示例："型糖尿病的典型症状"、"其他可能疾病"）
- 不要输出症状、检查项、科室、生活方式建议
- 只输出 JSON，不要解释

输出格式：
{{"drugs": ["阿莫西林", "布洛芬"], "diseases": ["2型糖尿病", "高血压"]}}

回答内容：
{text}
JSON："""


def extract_by_llm(llm, text: str) -> Dict[str, List[str]]:
    """用大模型抽取实体名（更准），失败时由调用方回退到规则抽取。"""
    import json

    raw = llm.invoke(EXTRACT_PROMPT.format(text=text[:2000])).content.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").replace("json", "", 1).strip()
    data = json.loads(raw)
    drugs = _dedupe([str(x).strip() for x in (data.get("drugs") or []) if str(x).strip()])
    diseases = _dedupe([str(x).strip() for x in (data.get("diseases") or []) if str(x).strip()])
    return {"drugs": drugs, "diseases": diseases}


# ---------------- 判定 ----------------


def build_matcher(whitelist: set):
    """构造「是否被图谱覆盖」的判定函数。

    不能只做精确匹配：图谱里存的是「二甲双胍口服」「原发性高血压」这种规范全称，
    而回答里写「二甲双胍」「高血压」同样正确。所以再加一层双向包含判定，
    但要求长度足够（≥2 字）避免 "1型糖尿病" 和 "2型糖尿病" 这类被误判成同一个。
    """
    white = {w for w in whitelist if w}

    def covered(term: str) -> bool:
        if not term or len(term) < 2:
            return False
        if term in white:
            return True
        for w in white:
            if len(w) < 2:
                continue
            if term in w or w in term:
                return True
        return False

    return covered


def judge(mentions: Dict[str, List[str]], whitelist: set, source: str) -> Dict:
    """按图谱白名单判定越界（= 图谱里没有 → 疑似编造）。"""
    covered = build_matcher(whitelist)
    drugs = mentions.get("drugs", [])
    diseases = mentions.get("diseases", [])
    all_terms = drugs + diseases
    illegal = [t for t in all_terms if not covered(t)]
    total = len(all_terms)
    return {
        "drugs": drugs,
        "diseases": diseases,
        "illegal": illegal,
        "total": total,
        "illegal_count": len(illegal),
        "illegal_rate": round(len(illegal) / total, 3) if total else 0.0,
        "method": source,
    }


def check(text: str, whitelist: set, llm=None) -> Dict:
    """抽取 + 判定。llm 传了就用大模型抽取，失败回退规则。"""
    if llm is not None:
        try:
            return judge(extract_by_llm(llm, text), whitelist, "llm")
        except Exception:  # noqa: BLE001  抽取失败就退回规则
            pass
    return judge(extract_by_rules(text), whitelist, "rule")
