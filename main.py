"""命令行交互入口：像聊天一样使用疾病辅助诊断智能体。

用法：
    python main.py            # 进入交互对话
    python main.py --demo     # 跑两个内置示例（不需要手动输入）
    python main.py --once "我最近老是口渴、尿多，还瘦了"   # 只问一句

可用指令（交互模式）：
    reset   清空当前会话记忆
    q       退出
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents import chain as chat_chain
from agents.pipeline import run_pipeline

SESSION = "cli"
LINE = "=" * 72


def banner():
    print(LINE)
    print("  疾病辅助诊断智能体  |  症状自查 · 疾病百科")
    print("  输入身体不适的描述即可，例如：我最近老是口渴、尿多，还瘦了")
    print("  指令：reset 清空记忆   q 退出")
    print(LINE)
    print("  ⚠️  辅助自查参考，不能替代执业医师诊断，如有不适请及时就医")
    print(LINE)


def show(user_text: str):
    """跑一次完整流水线并打印。闲聊走带记忆的对话链。"""
    result = run_pipeline(user_text)
    perception = result["perception"]
    retrieval = result["retrieval"]
    diag = result["diagnosis"]

    print(f"\n[感知] 意图={perception['intent']}  实体={perception['entities']}")

    if retrieval.get("hit"):
        d = retrieval.get("disease") or {}
        print(f"[检索] 命中方式={retrieval.get('mode')} —— {retrieval.get('reason')}")
        print(f"       疾病={d.get('name')}（常用名：{d.get('alias1') or '—'}）"
              f"  科室={d.get('department') or '—'}")
        if retrieval.get("candidates"):
            print("       候选排序：" + " | ".join(
                f"{c['name']}(命中{c['hits']}个/{c['coverage']:.0%})" for c in retrieval["candidates"]))
        if retrieval.get("differential"):
            print("       需要鉴别：" + " | ".join(
                f"{x.get('name')}(共享:{'/'.join(x.get('shared') or [])})" for x in retrieval["differential"]))
    else:
        print(f"[检索] 未命中图谱 —— {retrieval.get('reason')}")

    print(f"[诊断] {diag.get('root_cause')}  |  置信度={diag.get('confidence')}")

    # 闲聊场景：直接用带记忆的对话链回答，不套报告模板
    if perception["intent"] == "闲聊" and not retrieval.get("hit"):
        print(f"\n助手：{chat_chain.chat(user_text, session_id=SESSION)}")
        return

    print(f"\n{LINE}\n{result['report']}\n{LINE}")
    print(f"（耗时 {result['timing']['total_s']}s：感知 {result['timing']['perception_s']}s / "
          f"检索 {result['timing']['retrieval_s']}s / 诊断 {result['timing']['diagnosis_s']}s / "
          f"报告 {result['timing']['report_s']}s）")


DEMOS = [
    "我最近老是口渴、尿多，还瘦了，是不是糖尿病？",
    "消渴病患者平时应该注意什么？",
]


def main():
    args = sys.argv[1:]

    if "--demo" in args:
        for text in DEMOS:
            print(f"\n{'#' * 72}\n问：{text}\n{'#' * 72}")
            show(text)
        return

    if "--once" in args:
        idx = args.index("--once")
        text = args[idx + 1] if len(args) > idx + 1 else "".join(args[idx + 1:])
        if not text:
            print("用法：python main.py --once \"你的问题\"")
            return
        show(text)
        return

    banner()
    while True:
        try:
            text = input("\n你：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break
        if not text:
            continue
        if text in ("q", "quit", "exit"):
            print("再见！")
            break
        if text == "reset":
            chat_chain.reset(SESSION)
            print("已清空会话记忆。")
            continue
        show(text)


if __name__ == "__main__":
    main()
