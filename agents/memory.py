from langchain.memory import ConversationBufferMemory
from langchain_community.chat_message_histories import ChatMessageHistory


class MemoryManager:
    """封装 Memory 组件，支持按 session_id 隔离多会话。"""

    def __init__(self):
        self._store = {}  # session_id -> ChatMessageHistory

    def get_memory(self, session_id: str = "default", k: int = 10) -> ConversationBufferMemory:
        """获取/创建某个会话的 Memory。k=保留最近几轮。"""
        if session_id not in self._store:
            # 如果该会话id不存在，新建一个 ChatMessageHistory 实例存入字典
            self._store[session_id] = ChatMessageHistory()
        return ConversationBufferMemory(
            chat_memory=self._store[session_id],
            memory_key="history",
            return_messages=True,
            k=k,
        )

    def clear(self, session_id: str):
        """清空某会话记忆。"""
        if session_id in self._store:
            self._store[session_id].clear()


# 全局单例
memory_manager = MemoryManager()
