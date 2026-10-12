"""Neo4j 连接管理: 单例 Graph，全期复用。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from py2neo import Graph

_graph = None

def get_graph() -> Graph:
    """获取全局唯一的 Graph 连接（懒加载单例）。

    注意：不传 name（数据库名）。Neo4j 3.5 不支持 4.0+ 的「多数据库选择」，
    传 name= 会抛 "Database selection is not supported prior to Neo4j 4.0"。
    这里走服务端默认数据库（即 .env 中 NEO4J_DATABASE=neo4j），3.5 / 4.x / 5.x 均可用。
    """
    global _graph
    if _graph is None:
        _graph = Graph(
            config.NEO4J_URI,
            auth=(config.NEO4J_USER, config.NEO4J_PASSWORD),
        )
    return _graph