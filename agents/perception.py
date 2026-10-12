"""感知角色：把用户自然语言转成「意图 + 实体」。

- 意图：疾病诊断 / 知识查询 / 闲聊
- 实体：disease（疾病名或常用名）、symptom（症状列表，可多个）

设计要点：
1. 用大模型抽取，temperature=0 保证输出稳定；
2. 大模型抽不出实体时，用图谱词表做规则兜底（病名/别名、症状词）；
3. 返回的 raw 是「用户原话」，供检索层兜底使用。
"""
import os
import sys
import json
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain.prompts import PromptTemplate

from agents.llm import get_llm
from neo4j_tools.retriever import list_disease_names, list_symptom_names

INTENTS = ["疾病诊断", "知识查询", "闲聊"]

# 口语 → 图谱规范名 的同义词表。
# 图谱里存的是医学规范词（多饮/多尿/体重下降），而用户说的是口语（口渴/尿多/瘦了），
# 因此感知层必须做一层归一，否则「有病说不出」——实体抽到了却检索不到。
SYNONYMS = {
    # 症状
    "口渴": "多饮", "口很渴": "多饮", "老想喝水": "多饮", "喝水多": "多饮", "口干": "多饮",
    "尿多": "多尿", "尿频": "多尿", "夜尿多": "多尿", "小便多": "多尿", "排尿多": "多尿",
    "瘦了": "体重下降", "消瘦": "体重下降", "体重减轻": "体重下降", "掉秤": "体重下降", "变瘦": "体重下降",
    "没力气": "乏力", "疲乏": "乏力", "无力": "乏力", "浑身没劲": "乏力", "容易累": "乏力",
    "头昏": "头晕", "眩晕": "头晕",
    "头疼": "头痛",
    "心慌": "心悸", "心跳快": "心悸", "心跳加快": "心悸",
    "发烧": "发热", "体温高": "发热", "低烧": "发热",
    "咳": "咳嗽",
    "嗓子疼": "咽痛", "喉咙痛": "咽痛", "嗓子痛": "咽痛",
    # 疾病
    "糖尿病": "2型糖尿病", "消渴": "2型糖尿病",
    "高血压": "原发性高血压", "血压高": "原发性高血压", "血压升高": "原发性高血压",
    "流感": "流行性感冒", "感冒": "流行性感冒",
}

PERCEIVE_PROMPT = """从下面的用户输入中抽取意图和实体，只输出 JSON，不要解释。

意图只能取以下三种之一：疾病诊断、知识查询、闲聊。
- 描述身体不适、想了解自己可能得了什么病 → 疾病诊断
- 直接问某个疾病的知识（症状、治疗、预防、挂什么科） → 知识查询
- 打招呼、与医疗无关 → 闲聊

实体字段：
- disease：提到的疾病名称或常用名（如「糖尿病」「消渴病」），没有给 null
- symptom：提到的症状名称数组（如 ["多饮", "多尿"]），没有给 []

示例：
输入：我最近老是口渴、尿多，还瘦了
输出：{{"intent": "疾病诊断", "entities": {{"disease": null, "symptom": ["多饮", "多尿", "体重下降"]}}}}

输入：消渴病平时要注意什么
输出：{{"intent": "知识查询", "entities": {{"disease": "消渴病", "symptom": []}}}}

用户输入：{input}
JSON："""

_TEMPLATE = PromptTemplate(input_variables=["input"], template=PERCEIVE_PROMPT)


def normalize_symptom(word, vocab):
    """把口语症状名归一成图谱规范名；不在词表里就返回 None。"""
    if not word:
        return None
    word = str(word).strip()
    if word in vocab:
        return word
    canon = SYNONYMS.get(word)
    if canon and canon in vocab:
        return canon
    return None


def _rule_extract(user_text: str) -> Dict:
    """规则兜底：直接在原文里找病名/别名和症状词（含口语同义词）。"""
    entities = {}

    # 病名 / 别名匹配（长名优先，避免「高血压」被「血压升高」这类短别名抢先）
    for item in list_disease_names():
        names = [item.get("name"), item.get("alias1"), item.get("alias2")]
        for n in sorted([x for x in names if x], key=len, reverse=True):
            if n in user_text:
                entities["disease"] = n
                break
        if entities.get("disease"):
            break

    # 症状词匹配：先认图谱规范名，再认口语同义词
    vocab = list_symptom_names()
    hits = [s for s in vocab if s in user_text]
    for slang, canon in SYNONYMS.items():
        if slang in user_text and canon in vocab and canon not in hits:
            hits.append(canon)
    if hits:
        entities["symptom"] = hits

    return entities


def perceive(user_text: str) -> Dict:
    """感知入口：返回 {intent, entities, raw}。"""
    entities: Dict = {}
    intent = "闲聊"

    try:
        llm = get_llm(temperature=0.0)
        raw = llm.predict(_TEMPLATE.format(input=user_text)).strip()
        # 容错：模型可能裹上 markdown 代码块
        if raw.startswith("```"):
            raw = raw.strip("`").replace("json", "", 1).strip()
        data = json.loads(raw)
        intent = data.get("intent") or "闲聊"
        entities = {k: v for k, v in (data.get("entities") or {}).items() if v}
    except Exception:
        # 大模型不可用 / 输出不是 JSON：走规则，保证流程不断
        intent = "闲聊"

    # 规范化症状字段为 list
    if entities.get("symptom") and isinstance(entities["symptom"], str):
        entities["symptom"] = [entities["symptom"]]

    # 症状归一：口语 → 规范名（口渴→多饮、尿多→多尿、瘦了→体重下降），
    # 并丢掉图谱里确实没有的词，避免检索空转
    vocab = list_symptom_names()
    if entities.get("symptom"):
        normalized, seen = [], set()
        for s in entities["symptom"]:
            canon = normalize_symptom(s, vocab)
            if canon and canon not in seen:
                seen.add(canon)
                normalized.append(canon)
        entities["symptom"] = normalized

    # 疾病名归一：模型常返回常用名（糖尿病/高血压），统一成图谱规范名
    if entities.get("disease"):
        d = str(entities["disease"]).strip()
        entities["disease"] = SYNONYMS.get(d, d)

    # 大模型没抽出有效实体 → 规则兜底
    if not entities.get("disease") and not entities.get("symptom"):
        entities = _rule_extract(user_text)

    if intent not in INTENTS:
        intent = "疾病诊断" if entities else "闲聊"

    return {"intent": intent, "entities": entities, "raw": user_text}
