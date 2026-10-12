"""接口路由。

沿用参考项目的 6 个基础接口，另加 3 个自研接口（创新点）：
  subgraph/   命中疾病的一跳子图（前端画图）
  symptoms/   症状词表（前端联想输入 / 归一校验）
  evaluate/   双模式对照实验（纯大模型 vs 图谱增强，量化幻觉率）
"""
from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("graph/stats/", views.graph_stats, name="graph-stats"),
    path("graph/subgraph/", views.graph_subgraph, name="graph-subgraph"),
    path("retrieve/", views.retrieve, name="retrieve"),
    path("diagnose/", views.diagnose, name="diagnose"),
    path("chat/", views.chat, name="chat"),
    path("chat/reset/", views.chat_reset, name="chat-reset"),
    path("symptoms/", views.symptoms, name="symptoms"),
    path("evaluate/", views.evaluate, name="evaluate"),
]
