"""诊断角色：调用大模型 + 图谱工具，产出结构化诊断结论。

返回 JSON 结构：
{
    "possible_diseases": [{"name": ..., "confidence": ..., "reason": ...}],
    "root_cause": "主要考虑",
    "evidence": ["依据1", "依据2"],
    "confidence": 0.0~1.0,
    "solutions": [{"name": ..., "steps": ..., "cost": ...}],
    "department": "推荐科室",
    "differential": ["需要区分的疾病"],
    "need_more_info": bool,
    "follow_up_questions": ["还缺哪些信息"]
}
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import SystemMessage

from agents.llm import get_llm
from agents.tools import graph_search_tool

DIAGNOSIS_SYSTEM = """你是一名疾病辅助诊断智能体，服务于普通用户的症状自查，不是执业医师。

工作流程：
1. 判断用户意图：疾病诊断 / 知识查询 / 闲聊
2. 只要涉及症状、疾病、治疗、预防、就诊科室，必须先调用 graph_search_tool 查知识图谱
3. 严格依据图谱返回的数据推理，不要编造图谱里没有的疾病、药物或剂量
4. 用户描述多个症状时，按「命中症状数」对候选疾病排序，并在 differential 里列出症状重叠、需要鉴别的疾病
5. 信息不足时（例如只说了 1 个非特异症状），need_more_info 置 true 并给出 follow_up_questions
6. confidence 表示与图谱的匹配程度，不是医学确诊概率，最高不超过 0.9

输出必须是一个严格 JSON（不要 markdown 代码块、不要多余解释），结构如下：
{
  "possible_diseases": [{"name": "疾病名", "confidence": 0.0, "reason": "判断依据"}],
  "root_cause": "主要考虑",
  "evidence": ["来自图谱的依据"],
  "confidence": 0.0,
  "solutions": [{"name": "方案名", "steps": "步骤", "cost": "费用"}],
  "department": "推荐就诊科室",
  "differential": ["需要鉴别的疾病"],
  "need_more_info": false,
  "follow_up_questions": []
}

若图谱未命中：基于通用医学常识回答，confidence 不超过 0.4，并把 need_more_info 置 true。
若为闲聊：直接友好回应，这时可以不用 JSON。"""

DISCLAIMER = "以上为辅助自查参考，不能替代执业医师的诊断，如有不适请及时就医。"

# 已经拿到图谱检索结果时，直接让大模型基于「给定事实」推理，
# 不再走 Agent 循环 —— 避免同一个问题被检索两遍（流水线里已检索过一次）。
DIRECT_PROMPT = """你是疾病辅助诊断智能体，面向普通用户的症状自查，不是执业医师。

下面是从疾病知识图谱里检索到的**事实数据**（严格以此为依据，不要编造图谱之外的疾病、药物或剂量）：

{retrieval}

用户的问题：{input}

请输出严格 JSON（不要 markdown 代码块、不要多余解释）：
{{
  "possible_diseases": [{{"name": "疾病名", "confidence": 0.0, "reason": "判断依据"}}],
  "root_cause": "主要考虑",
  "evidence": ["来自上述图谱数据的依据"],
  "confidence": 0.0,
  "solutions": [{{"name": "方案名", "steps": "步骤", "cost": "费用"}}],
  "department": "推荐就诊科室",
  "differential": ["需要鉴别的疾病"],
  "need_more_info": false,
  "follow_up_questions": []
}}

规则：
- 用户描述多个症状时，按命中症状数排序候选疾病；图谱里给了 differential 就填进来
- **confidence 表示与图谱的匹配程度，不是医学确诊概率，最高不超过 0.9**
- 绝对不要编造图谱之外的疾病名、药物名、剂量或用法用量（图谱没写剂量就不要写）
- 图谱数据不足以支撑判断时，confidence 不超过 0.4，need_more_info 置 true
- 如果图谱为空且用户只是闲聊，直接友好回应，不必输出 JSON
JSON："""


def _diagnose_with_retrieval(user_text: str, retrieval: dict) -> dict:
    """基于已有检索结果直接推理（不重复调工具）。"""
    from langchain_core.messages import HumanMessage

    llm = get_llm(temperature=0.2)
    brief = json.dumps(
        {
            "mode": retrieval.get("mode"),
            "reason": retrieval.get("reason"),
            "disease": retrieval.get("disease"),
            "symptoms": retrieval.get("symptoms"),
            "solutions": retrieval.get("solutions"),
            "preventions": retrieval.get("preventions"),
            "causes": retrieval.get("causes"),
            "department": retrieval.get("department"),
            "candidates": retrieval.get("candidates"),
            "differential": retrieval.get("differential"),
        },
        ensure_ascii=False,
    )
    raw = llm.invoke([HumanMessage(content=DIRECT_PROMPT.format(retrieval=brief, input=user_text))]).content
    result = _parse(raw)
    result.setdefault("disclaimer", DISCLAIMER)
    return result



def build_diagnosis_agent() -> AgentExecutor:
    """构建诊断 Agent 执行器。"""
    llm = get_llm()
    tools = [graph_search_tool]

    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=DIAGNOSIS_SYSTEM),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    agent = create_tool_calling_agent(llm, tools, prompt)
    # max_iterations 限制迭代次数，防止 Agent 反复检索把 token 烧光
    return AgentExecutor(agent=agent, tools=tools, verbose=False, max_iterations=5)


def _clamp_confidence(data: dict) -> dict:
    """兜底钳位：自查场景不允许出现「100% 确诊」这种表述。"""
    try:
        c = float(data.get("confidence", 0) or 0)
    except (TypeError, ValueError):
        c = 0.0
    data["confidence"] = max(0.0, min(c, 0.9))
    return data


def _parse(raw: str) -> dict:
    """解析 Agent 输出，失败时降级为可读结构而不是抛异常。"""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`").replace("json", "", 1).strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return _clamp_confidence(data)
    except json.JSONDecodeError:
        pass
    return {
        "possible_diseases": [],
        "root_cause": text,
        "evidence": [],
        "confidence": 0.3,
        "solutions": [],
        "department": "",
        "differential": [],
        "need_more_info": True,
        "follow_up_questions": [],
    }


def diagnose(user_text: str, chat_history=None, retrieval=None) -> dict:
    """诊断入口：返回结构化 dict。

    传了 retrieval（流水线里已经检索好的图谱数据）→ 直接基于事实推理，不重复检索；
    没传 → 走 Agent 循环，由模型自己决定何时调用检索工具。
    """
    if retrieval is not None:
        return _diagnose_with_retrieval(user_text, retrieval)

    executor = build_diagnosis_agent()
    raw = executor.invoke({
        "input": user_text,
        "chat_history": chat_history or [],
    })["output"]
    result = _parse(raw)
    result.setdefault("disclaimer", DISCLAIMER)
    return result
