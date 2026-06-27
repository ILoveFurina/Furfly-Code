"""视图辅助 — 聊天块、状态栏与错误的渲染函数。"""

from __future__ import annotations

from rich.markdown import Markdown
from rich.text import Text


def user_block(text: str) -> Text:
    """为 RichLog 渲染用户消息块。"""
    return Text(f"● {text}", style="bold")


def assistant_block(reply: str) -> Markdown:
    """将已完成的助手回复按 markdown 渲染后写入 RichLog。"""
    return Markdown(reply)


def error_block(err: Exception) -> Text:
    """为 RichLog 渲染错误消息块。"""
    return Text(f"● Error: {err}", style="bold red")


def status_bar_text(provider_name: str, model_name: str, width: int) -> Text:
    """构建双列状态栏：左侧名称，右侧模型。

    参数：
        provider_name: 左侧显示文本。
        model_name: 右侧显示文本。
        width: 用于右对齐的总宽度。

    返回：
        包含两侧文本的 Rich Text 对象。
    """
    left = f" {provider_name}"
    right = f"{model_name} "
    padding = max(width - len(left) - len(right), 0)
    return Text(left + " " * padding + right)


def streaming_text(cur_reply: str, elapsed_seconds: float) -> Text:
    """构建动态流式显示区域内容。

    展示目前为止的增量文本，并附带一个计时的 "Imagining…" 提示。
    """
    imagining = Text(f"Imagining… ({int(elapsed_seconds)}s)", style="dim italic")
    if not cur_reply:
        # 等待首个 token — 只显示提示。
        return imagining
    return Text.assemble(cur_reply, "\n", imagining)
