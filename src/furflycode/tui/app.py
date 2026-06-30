"""furflycodeApp — 带状态机的 Textual 聊天应用。"""

from __future__ import annotations

import asyncio
import os
import time
from enum import Enum
from typing import TYPE_CHECKING

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.timer import Timer
from textual.widgets import OptionList, RichLog, Static, TextArea

from furflycode import __version__
from furflycode.config import ProviderConfig
from furflycode.conversation import Conversation
from furflycode.llm import Provider, new_provider
from furflycode.prompt import render_banner
from furflycode.tool import Registry
from furflycode.tui.select import ProviderSelect
from furflycode.tui.stream import consume_agent_events, tick
from furflycode.tui.view import status_bar_text, user_block

if TYPE_CHECKING:
    from furflycode.tui.stream import ToolDisplay


class SessionState(Enum):
    """顶层会话状态机。"""

    SELECTING = "selecting"  # 在多个 provider 之间选择
    IDLE = "idle"  # 等待用户输入
    STREAMING = "streaming"  # 等待/接收模型流


class PromptInput(TextArea):
    """多行输入框：Enter 发送，Alt+Enter 插入换行。"""

    DEFAULT_CSS = """
    PromptInput {
        height: 5;
        border: solid $primary;
        border-title-color: $text;
        padding: 0 1;
    }
    PromptInput:focus {
        border: solid $accent;
    }
    """

    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self.border_title = "❯ Send a message... (Enter to send, Alt+Enter for newline)"

    class Submitted(Message):
        """用户按 Enter 提交时发送。"""

        def __init__(self, text: str) -> None:
            self.text = text
            super().__init__()

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            # Enter 提交 — 阻止 TextArea 插入换行
            event.stop()
            text = self.text
            if text.strip():
                self.post_message(self.Submitted(text))
            return
        if event.key == "alt+enter":
            # Alt+Enter 在光标处插入换行
            event.stop()
            self._insert_newline()
            return
        # 其他按键：交给 TextArea 默认处理
        await super()._on_key(event)

    def _insert_newline(self) -> None:
        """在当前光标位置插入换行符。"""
        row, col = self.cursor_location
        lines = self.text.split("\n")
        line = lines[row]
        lines[row] = line[:col] + "\n" + line[col:]
        self.text = "\n".join(lines)
        self.cursor_location = (row + 1, 0)


class furflycodeApp(App):  # noqa: N801 — 名称由 spec 固定
    """主终端应用。"""

    CSS = """
    Screen {
        layout: vertical;
    }
    #log {
        height: 1fr;
        width: 1fr;
        padding: 0 1;
    }
    #streaming {
        height: auto;
        width: 1fr;
        padding: 0 1;
    }
    #input {
        width: 1fr;
        margin: 0 1 0 1;
    }
    #statusbar {
        height: 1;
        width: 1fr;
        background: $boost;
        color: $text;
        padding: 0 1;
    }
    ProviderSelect {
        display: none;
        height: 1fr;
        width: 1fr;
        margin: 1 2;
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", priority=True),
        Binding("escape", "cancel_loop", "Cancel", priority=True),
    ]

    def __init__(
        self,
        providers: list[ProviderConfig],
        registry: Registry | None = None,
        max_iterations: int = 20,
    ) -> None:
        super().__init__()
        self.providers = providers
        self._tool_registry: Registry = registry if registry is not None else Registry()
        self.state = SessionState.IDLE
        self.provider: Provider | None = None
        self.conv = Conversation()
        self.cur_reply = ""
        self.turn_start = 0.0
        self._cur_tool: ToolDisplay | None = None  # 执行中工具指示
        self._stream_task: asyncio.Task[None] | None = None
        self._timer: Timer | None = None
        self.plan_mode: bool = False  # Plan Mode：True 只放只读工具
        self.max_iterations = max_iterations  # Agent 循环兜底上限

    # ────────────── layout ──────────────
    def compose(self) -> ComposeResult:
        yield RichLog(id="log", wrap=True, markup=True)
        yield Static(id="streaming")
        yield PromptInput(id="input")
        yield ProviderSelect(self.providers)
        yield Static(id="statusbar")

    def on_mount(self) -> None:
        log = self.query_one("#log", RichLog)
        log.write(render_banner(__version__, os.getcwd()))

        if len(self.providers) == 1:
            self.provider = new_provider(self.providers[0])
            self.state = SessionState.IDLE
            self._update_statusbar()
            self.query_one("#input").focus()
        else:
            self._enter_selecting()

    # ────────────── provider selection ──────────────
    def _enter_selecting(self) -> None:
        """展示 provider 列表，隐藏聊天相关控件。"""
        self.state = SessionState.SELECTING
        self.query_one("#log").display = False
        self.query_one("#streaming").display = False
        self.query_one("#input").display = False
        select = self.query_one(ProviderSelect)
        select.display = True
        select.focus()

    def _exit_selecting(self, config: ProviderConfig) -> None:
        """隐藏 provider 列表并进入聊天。"""
        self.provider = new_provider(config)
        self.query_one(ProviderSelect).display = False
        self.query_one("#log").display = True
        self.query_one("#streaming").display = True
        self.query_one("#input").display = True
        self.state = SessionState.IDLE
        self._update_statusbar()
        self.query_one("#input").focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if self.state != SessionState.SELECTING:
            return
        option = event.option
        if option.id is None:
            return
        config = self.providers[int(option.id)]
        self._exit_selecting(config)

    # ────────────── input / submit ──────────────
    async def on_prompt_input_submitted(self, event: PromptInput.Submitted) -> None:
        await self.submit(event.text)

    async def submit(self, text: str) -> None:
        """处理一条用户提交的消息。"""
        stripped = text.strip()
        if stripped == "/exit":
            await self.action_quit()
            return
        if stripped == "/plan":
            # 切到 Plan Mode：只放只读工具，模型只探查不改
            if self.state != SessionState.IDLE or self.provider is None:
                return
            self.plan_mode = True
            self.query_one("#input", PromptInput).text = ""
            self.query_one("#log", RichLog).write(
                Text("── PLAN MODE（只读工具）· /do 切回 ──", style="bold yellow")
            )
            self._update_statusbar()
            return
        if stripped == "/do":
            if self.state != SessionState.IDLE or self.provider is None:
                return
            self.plan_mode = False
            self.query_one("#input", PromptInput).text = ""
            self.query_one("#log", RichLog).write(
                Text("── FULL MODE（全工具）──", style="bold green")
            )
            self._update_statusbar()
            return
        if self.state != SessionState.IDLE or self.provider is None:
            # 流式输出中忽略新提交 — 保留已输入的文字
            return

        self.conv.add_user(text)
        self.query_one("#log", RichLog).write(user_block(text))
        # 接受本轮后清空输入框
        self.query_one("#input", PromptInput).text = ""

        self.cur_reply = ""
        self.turn_start = time.monotonic()
        self.state = SessionState.STREAMING

        self._stream_task = asyncio.create_task(consume_agent_events(self))
        self._timer = self.set_interval(0.1, lambda: tick(self))

    # ────────────── status bar ──────────────
    def _update_statusbar(self) -> None:
        if self.provider is None:
            return
        bar = self.query_one("#statusbar", Static)
        width = max(self.size.width, 20)
        bar.update(
            status_bar_text(
                self.provider.name, self.provider.model, width, self.plan_mode
            )
        )

    def on_resize(self, event: events.Resize) -> None:
        self._update_statusbar()

    # ────────────── cancel / quit ──────────────
    async def action_cancel_loop(self) -> None:
        """Esc：循环中取消本轮（区别于 Ctrl+C 退出），复位到 IDLE。"""
        if self.state != SessionState.STREAMING:
            return
        if self._stream_task is not None and not self._stream_task.done():
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        log = self.query_one("#log", RichLog)
        if self.cur_reply.strip():
            log.write(Text(self.cur_reply, style="dim"))
        log.write(Text("  ⏹ 已取消", style="bold yellow"))
        self._stream_task = None
        self._cur_tool = None
        self.cur_reply = ""
        self.query_one("#streaming", Static).update("")
        self.state = SessionState.IDLE
        self.query_one("#input").focus()

    async def action_quit(self) -> None:
        if self._stream_task is not None and not self._stream_task.done():
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self.exit()
