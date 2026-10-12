"""视图层：REST 接口。

统一约定：
- 入参 JSON，取 text 字段
- 业务异常 → 502 + stage（pipeline / retrieval / llm / import）
- 参数错误 → 400
"""
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import services


def _read_text(request) -> str:
    return str(request.data.get("text") or "").strip()


def _bad_request(detail: str) -> Response:
    return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)


def _upstream_error(exc: services.ServiceError) -> Response:
    """智能体侧出错：502（对端服务失败），并标出出错阶段便于定位。"""
    return Response(
        {
            "detail": str(exc),
            "stage": exc.stage,
            "hint": "检查 Neo4j 是否启动、DASHSCOPE_API_KEY 是否有效、项目根 .env 是否被加载",
        },
        status=status.HTTP_502_BAD_GATEWAY,
    )


def _check_text(request):
    """公共校验：非空 + 长度上限。返回 (text, error_response)。"""
    text = _read_text(request)
    if not text:
        return None, _bad_request("text 不能为空")
    if len(text) > settings.MAX_INPUT_LEN:
        return None, _bad_request(f"text 过长，最多 {settings.MAX_INPUT_LEN} 字")
    return text, None


@api_view(["GET"])
def health(request):
    """GET /api/health/?probe=0 可跳过 Neo4j 连接（离线自检用）。"""
    probe = request.query_params.get("probe", "1") != "0"
    return Response(services.health(probe_neo4j=probe))


@api_view(["GET"])
def graph_stats(request):
    """GET /api/graph/stats/ 图谱规模统计。"""
    return Response(services.graph_stats())


@api_view(["GET"])
def graph_subgraph(request):
    """GET /api/graph/subgraph/?name=2型糖尿病 取一跳子图（前端可视化用）。"""
    name = (request.query_params.get("name") or "").strip()
    try:
        return Response(services.graph_subgraph(name))
    except services.ServiceError as exc:
        return _upstream_error(exc)


@api_view(["GET"])
def symptoms(request):
    """GET /api/symptoms/ 症状词表（前端联想输入）。"""
    try:
        return Response(services.symptoms())
    except services.ServiceError as exc:
        return _upstream_error(exc)


@api_view(["POST"])
def retrieve(request):
    """POST /api/retrieve/ 只做 感知 + 图谱检索，不跑大模型诊断。"""
    text, err = _check_text(request)
    if err:
        return err
    try:
        return Response(services.retrieve_only(text))
    except services.ServiceError as exc:
        return _upstream_error(exc)


@api_view(["POST"])
def diagnose(request):
    """POST /api/diagnose/ 跑完整四角色流水线（图谱检索 + 大模型推理 + 报告）。"""
    text, err = _check_text(request)
    if err:
        return err
    try:
        return Response(services.run_full(text, verbose=bool(request.data.get("verbose"))))
    except services.ServiceError as exc:
        return _upstream_error(exc)


@api_view(["POST"])
def chat(request):
    """POST /api/chat/ 带记忆的多轮对话。"""
    text, err = _check_text(request)
    if err:
        return err
    session_id = str(request.data.get("session_id") or "web")[:64]
    try:
        return Response(services.chat_once(text, session_id=session_id))
    except services.ServiceError as exc:
        return _upstream_error(exc)


@api_view(["POST"])
def chat_reset(request):
    """POST /api/chat/reset/ 清空指定会话记忆。"""
    session_id = str(request.data.get("session_id") or "web")[:64]
    try:
        services.reset_session(session_id)
    except services.ServiceError as exc:
        return _upstream_error(exc)
    return Response({"session_id": session_id, "cleared": True})


@api_view(["POST"])
def evaluate(request):
    """POST /api/evaluate/ 双模式对照实验（创新点）。

    入参：{"questions": ["...", "..."]}，不传则用内置默认问题。
    """
    questions = request.data.get("questions")
    if questions is not None and not isinstance(questions, list):
        return _bad_request("questions 必须是字符串数组")
    try:
        return Response(services.evaluate(questions))
    except services.ServiceError as exc:
        return _upstream_error(exc)
