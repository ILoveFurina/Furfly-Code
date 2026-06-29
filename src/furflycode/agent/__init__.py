"""agent 包 — 单轮闭环编排。

承载「请求#1（带工具）→ 收集工具调用 → 注册中心执行 → 结果回灌进 Conversation
→ 请求#2（续答）→ 最终文本 → 停」。对外吐出一条 Event async generator 供 TUI 渲染。
只依赖 llm、tool、conversation，不 import anthropic/openai，保持协议无关。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum

from furflycode.conversation import Conversation
from furflycode.llm import Provider
from furflycode.message import ToolCall, ToolResult
from furflycode.tool import DEFAULT_TIMEOUT, Registry

"""
这里的Event都是面对TUI的数据类型
也就是说，这里yield出去的数据，都是给前端消费的。
"""


class Phase(Enum):
    """工具调用执行阶段。"""

    START = "start"  # 工具开始执行
    END = "end"  # 工具执行完毕


@dataclass
class ToolEvent:
    """一次工具调用的开始/结束（供 TUI 渲染工具行与结果摘要）。

    属性：
        name: 工具名。
        args: 参数预览（用于 ● name(args)）。
        phase: START / END。
        result: phase=END 时的结果摘要。
        is_error: phase=END 时是否错误。
    """

    name: str
    args: str = ""
    phase: Phase = Phase.START
    result: str = ""
    is_error: bool = False


@dataclass
class Event:
    """单轮闭环对外事件流元素，TUI 据非空字段分派渲染。

    属性：
        text: 文本增量（preamble 或最终答复）。
        tool: 工具调用开始/结束。
        done: 本轮结束。
        err: 出错（不中断会话）。
    """

    text: str = ""
    tool: ToolEvent | None = None
    done: bool = False
    err: Exception | None = None


def _preview_args(raw_json: str, maxlen: int = 80) -> str:
    """从 raw JSON 参数取简短预览（用于工具行显示）。"""
    s = raw_json.strip()
    if not s:
        return ""
    if len(s) <= maxlen:
        return s
    return s[: maxlen - 1] + "…"


class Agent:
    """持有 provider 与注册中心，执行单轮闭环。"""

    def __init__(self, provider: Provider, registry: Registry) -> None:
        self._provider = provider
        self._registry = registry

    async def run(self, conv: Conversation) -> AsyncIterator[Event]:
        """执行单轮闭环，async generator 吐出事件流。

        调用方 cancel() 该 task 即终止；工具执行经 asyncio.wait_for 受
        DEFAULT_TIMEOUT 约束（N1）。
        """
        defs = self._registry.definitions()

        # ─── 请求#1：实时转发文本增量、累积 preamble、收集工具调用 ───
        preamble = ""
        calls: list[ToolCall] = []
        async for ev in self._provider.stream(conv.messages(), defs):
            if ev.err is not None:
                yield Event(err=ev.err)
                return
            if ev.text:
                preamble += ev.text
                yield Event(text=ev.text)
            if ev.tool_calls:
                calls.extend(ev.tool_calls)
            if ev.done:
                break

        if not calls:
            # 纯文本回合：直接落库并结束。
            conv.add_assistant(preamble)
            yield Event(done=True)
            return

        # ─── 有工具调用：落 assistant 工具调用回合 ───
        conv.add_assistant_with_tool_calls(preamble, calls)

        # ─── 顺序执行每个调用（单轮内多工具顺序执行，F5） ───
        results: list[ToolResult] = []
        for call in calls:
            yield Event(
                tool=ToolEvent(
                    name=call.name,
                    args=_preview_args(call.input),
                    phase=Phase.START,
                )
            )
            r = await self._registry.execute(
                call.name, call.input, timeout=DEFAULT_TIMEOUT
            )
            yield Event(
                tool=ToolEvent(
                    name=call.name,
                    phase=Phase.END,
                    result=r.content,
                    is_error=r.is_error,
                )
            )
            results.append(
                ToolResult(
                    tool_call_id=call.id,
                    content=r.content,
                    is_error=r.is_error,
                )
            )

        # ─── 结果回灌 ───
        conv.add_tool_results(results)

        # ─── 请求#2：续答（最终文本）；忽略其返回的工具调用（单轮，AC9） ───
        final = ""
        async for ev in self._provider.stream(conv.messages(), defs):
            if ev.err is not None:
                yield Event(err=ev.err)
                return
            if ev.text:
                final += ev.text
                yield Event(text=ev.text)
            if ev.tool_calls:
                # 单轮上限：不再发起新一轮工具执行（AC9）。
                continue
            if ev.done:
                break

        if not final:
            # 空最终答复用占位提示（避免空 assistant 回合破坏下一轮请求）。
            final = "（本轮已达到单轮工具调用上限，未生成最终答复）"
        conv.add_assistant(final)
        yield Event(done=True)
