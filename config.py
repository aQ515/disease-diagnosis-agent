import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # LLM
    DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
    QWEN_MODEL_NAME = os.getenv("QWEN_MODEL_NAME", "qwen-plus")
    QWEN_TEMPERATURE = float(os.getenv("QWEN_TEMPERATURE", "0.3"))

    # Neo4j
    # 兼容 .env 中的两种写法：NEO4J_URI 或 NEO4J_URL
    NEO4J_URI = os.getenv("NEO4J_URI") or os.getenv("NEO4J_URL") or "bolt://localhost:7687"
    NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "123456")
    NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

    # MySQL
    MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "123456")
    MYSQL_DB = os.getenv("MYSQL_DB", "agent_db")

config = Config()
  