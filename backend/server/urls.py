"""URL 路由总入口。

根路径 `/` 放一个接口索引，避免直接访问 8001 看到 404 以为服务没起来。
"""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def index(request):
    """根路径：列出可用接口，方便手工验证。"""
    return JsonResponse(
        {
            "service": "graph-disease-diagnosis-api",
            "version": "1.0.0",
            "hint": "这是一个 JSON 接口服务，浏览器里没有页面；要看界面请访问前端 5174 端口。",
            "frontend": "http://<虚拟机IP>:5174/",
            "endpoints": {
                "GET  /api/health/": "探活（django / neo4j / llm）",
                "GET  /api/graph/stats/": "图谱规模统计",
                "GET  /api/graph/subgraph/?name=2型糖尿病": "一跳子图（可视化数据）",
                "GET  /api/symptoms/": "症状词表",
                "POST /api/retrieve/": '只做感知+图谱检索，body: {"text": "..."}',
                "POST /api/diagnose/": '完整四角色流水线，body: {"text": "..."}',
                "POST /api/chat/": '多轮对话，body: {"text": "...", "session_id": "web"}',
                "POST /api/chat/reset/": '清空会话，body: {"session_id": "web"}',
                "POST /api/evaluate/": '双模式对照实验，body: {"questions": ["..."]}',
                "GET  /admin/": "Django 后台",
            },
        },
        json_dumps_params={"ensure_ascii": False, "indent": 2},
    )


urlpatterns = [
    path("", index, name="index"),
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
]
