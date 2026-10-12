"""带记忆的多轮对话链（会话隔离）。

每个 session_id 一份独立记忆，多个用户可以同时使用而互不串话。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain.chains import ConversationChain
from langchain.prompts import PromptTemplate

from agents.llm import get_llm
from agents.memory import memory_manager

SYSTEM_PROMPT = """你是「图灵小助」，一名疾病辅助自查助手。

你的职责：
1. 理解用户描述的身体不适，必要时追问关键细节（症状持续多久、还有哪些伴随症状、既往病史）
2. 结合对话历史理解指代（例如用户说「它」「这个症状」，要知道指的是前文提到的症状）
3. 提醒用户你只是辅助自查，不能替代医生诊断，症状严重时应及时就医

当前对话历史：
{history}

用户：{input}
助手："""

PROMPT_TEMPLATE = PromptTemplate(
    input_variables=["history", "input"],
    template=SYSTEM_PROMPT,
)


def build_chat_chain(session_id: str = "default", k: int = 10) -> ConversationChain:
    """构建带记忆的对话链。k=保留最近几轮。"""
    llm = get_llm()
    memory = memory_manager.get_memory(session_id, k=k)
    return ConversationChain(
        llm=llm,
        memory=memory,
        prompt=PROMPT_TEMPLATE,
        verbose=False,
    )


def chat(user_input: str, session_id: str = "default") -> str:
    """便捷对话入口。"""
    return build_chat_chain(session_id).predict(input=user_input)


def reset(session_id: str = "default") -> None:
    """清空某个会话的记忆。"""
    memory_manager.clear(session_id)
