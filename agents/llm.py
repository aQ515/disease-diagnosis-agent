"""统一的大模型入口。

约定：
- API Key 只从环境变量 / .env 读取，禁止硬编码进源码
- 支持 temperature 参数（perception 等模块会以 0.0 调用以保证抽取稳定）
"""
import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# 兼容不同运行方式下的 .env 查找
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
load_dotenv()

DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen-turbo"


def get_llm(temperature: float = 0.1):
    """返回一个接入阿里云百炼（ OpenAI 兼容模式）的 ChatModel。

    Args:
        temperature: 采样温度，默认 0.1。传 0.0 可获得更确定性的输出。
    """
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "未读取到 DASHSCOPE_API_KEY，请检查项目根目录 .env 文件是否配置了该项。"
        )

    llm = ChatOpenAI(
        api_key=api_key,
        base_url=DASHSCOPE_BASE_URL,
        model=os.getenv("QWEN_MODEL_NAME", DEFAULT_MODEL),
        temperature=temperature,
    )
    return llm


if __name__ == "__main__":
    llm = get_llm()
    print("模型:", llm.model_name, "| 温度:", llm.temperature)
    print(llm.invoke("用一句话说明什么是知识图谱").content)
