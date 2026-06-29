"""Agent event consumption and timing logic for the TUI.

These functions are called from furflycodeApp with the app instance
as their first argument.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rich.markdown import Markdown
from rich.text import Text
from textual.widgets import RichLog, Static

from furflycode.agent import Agent, Event, Phase
from furflycode.tui.view import (
    error_block,
    streaming_text,
    tool_line,
    tool_result_summary,
    tool_running_text,
)

if TYPE_CHECKING:
    from furflycode.tui.app import furflycodeApp


@dataclass
class ToolDisplay:
    """执行中工具的展示信息。"""

    name: str
    args: str


async def consume_agent_events(app: furflycodeApp) -> None:
    """消费 agent.run 产出的事件流，实时更新 UI（F8/N2）。

    Launched as an asyncio.Task from the App.
    """
    assert app.provider is not None  # 由 submit 在 provider 非空时调用
    agent = Agent(app.provider, app._tool_registry)
    try:
        async for ev in agent.run(app.conv):
            await _dispatch(app, ev)
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001 — 不中断会话
        await _finish_with_error(app, e)


async def _dispatch(app: furflycodeApp, ev: Event) -> None:
    """按事件类型分派渲染。"""
    if ev.err is not None:
        await _finish_with_error(app, ev.err)
        return
    if ev.text:
        app.cur_reply += ev.text
        _refresh_streaming_view(app)
        return
    if ev.tool is not None:
        if ev.tool.phase == Phase.START:
            # 若有 preamble 文本，先提交到 scrollback 并清空动态区
            if app.cur_reply:
                app.query_one("#log", RichLog).write(Markdown(app.cur_reply))
                app.cur_reply = ""
            app._cur_tool = ToolDisplay(name=ev.tool.name, args=ev.tool.args)
            _refresh_streaming_view(app)
        else:  # Phase.END
            log = app.query_one("#log", RichLog)
            log.write(tool_line(ev.tool.name, ev.tool.args))
            log.write(tool_result_summary(ev.tool.result, ev.tool.is_error))
            app._cur_tool = None
            _refresh_streaming_view(app)
        return
    if ev.done:
        await _finish_with_assistant(app, app.cur_reply)
        return


def tick(app: furflycodeApp) -> None:
    """Timer callback — refresh the streaming indicator every ~100 ms."""
    from furflycode.tui.app import SessionState

    if app.state != SessionState.STREAMING:
        return
    elapsed = time.monotonic() - app.turn_start
    streaming_widget = app.query_one("#streaming", Static)
    if app._cur_tool is not None:
        streaming_widget.update(
            tool_running_text(app._cur_tool.name, app._cur_tool.args, elapsed)
        )
    else:
        streaming_widget.update(streaming_text(app.cur_reply, elapsed))


def _refresh_streaming_view(app: furflycodeApp) -> None:
    """Update the streaming area with the current reply buffer / tool indicator."""
    elapsed = time.monotonic() - app.turn_start
    streaming_widget = app.query_one("#streaming", Static)
    if app._cur_tool is not None:
        streaming_widget.update(
            tool_running_text(app._cur_tool.name, app._cur_tool.args, elapsed)
        )
    else:
        streaming_widget.update(streaming_text(app.cur_reply, elapsed))


async def _finish_with_assistant(app: furflycodeApp, reply: str) -> None:
    """Finalize a successful assistant turn.

    会话历史由 agent 维护，这里只负责渲染与状态复位。
    """
    from furflycode.tui.app import SessionState

    log = app.query_one("#log", RichLog)
    if reply.strip():
        log.write(Markdown(reply))
    elapsed = time.monotonic() - app.turn_start
    log.write(Text(f"  ({elapsed:.1f}s)", style="dim"))
    _stop_streaming(app)
    app.state = SessionState.IDLE
    app.query_one("#input").focus()


async def _finish_with_error(app: furflycodeApp, err: Exception) -> None:
    """Finalize a failed turn: display error, reset state."""
    from furflycode.tui.app import SessionState

    log = app.query_one("#log", RichLog)
    log.write(error_block(err))
    _stop_streaming(app)
    app.state = SessionState.IDLE
    app.query_one("#input").focus()


def _stop_streaming(app: furflycodeApp) -> None:
    """Stop the streaming timer and clear the streaming area."""
    if app._timer is not None:
        app._timer.stop()
        app._timer = None
    app._stream_task = None
    app._cur_tool = None
    app.cur_reply = ""
    streaming_widget = app.query_one("#streaming", Static)
    streaming_widget.update("")
