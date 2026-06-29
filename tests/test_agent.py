"""agent 包单测 — fake provider 驱动单轮闭环（AC8/AC9）。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from furflycode.agent import Agent, Event, Phase
from furflycode.conversation import Conversation
from furflycode.llm import StreamEvent, ToolCall, ToolDefinition
from furflycode.tool import new_default_registry


class FakeProvider:
    """按脚本分轮吐出 StreamEvent 的假 provider。

    每轮一个脚本（StreamEvent 列表）；按调用顺序切换。
    """

    def __init__(self, scripts: list[list[StreamEvent]]) -> None:
        self._scripts = list(scripts)
        self._call_count = 0

    @property
    def name(self) -> str:
        return "fake"

    @property
    def model(self) -> str:
        return "fake-model"

    async def stream(
        self, msgs: list[Any], tools: list[ToolDefinition]
    ) -> AsyncIterator[StreamEvent]:
        script = self._scripts[self._call_count]
        self._call_count += 1
        for ev in script:
            yield ev


def _events(agent: Agent, conv: Conversation) -> list[Event]:
    """同步收集 agent.run 产出的全部 Event（非 async 测试用）。"""
    import asyncio

    async def collect() -> list[Event]:
        out: list[Event] = []
        async for ev in agent.run(conv):
            out.append(ev)
        return out

    return asyncio.run(collect())


async def _events_async(agent: Agent, conv: Conversation) -> list[Event]:
    """在已有事件循环中收集 agent.run 产出（async 测试用）。"""
    out: list[Event] = []
    async for ev in agent.run(conv):
        out.append(ev)
    return out


async def test_single_turn_tool_loop_ac8():
    """请求#1 调 read_file、请求#2 给最终文本 → 含 START/END + 最终文本（AC8）。"""
    conv = Conversation()
    conv.add_user("读 a.txt 并总结")
    # 请求#1：先吐 preamble 文本，再吐工具调用，再 done
    script1 = [
        StreamEvent(text="let me read "),
        StreamEvent(text="that file"),
        StreamEvent(
            tool_calls=[ToolCall(id="t1", name="read_file", input='{"path":"a.txt"}')]
        ),
        StreamEvent(done=True),
    ]
    # 请求#2：最终文本
    script2 = [
        StreamEvent(text="文件内容已读取"),
        StreamEvent(text="，总结如下"),
        StreamEvent(done=True),
    ]
    provider = FakeProvider([script1, script2])
    registry = new_default_registry()
    agent = Agent(provider, registry)

    events = await _events_async(agent, conv)

    # 文本增量被转发
    text_joined = "".join(e.text for e in events if e.text)
    assert "let me read" in text_joined
    assert "文件内容已读取" in text_joined
    # 工具 START / END 各一次
    tool_events = [e for e in events if e.tool is not None]
    assert len(tool_events) == 2
    assert tool_events[0].tool.phase == Phase.START
    assert tool_events[0].tool.name == "read_file"
    assert tool_events[1].tool.phase == Phase.END
    # 最后 done
    assert events[-1].done
    # 会话历史末尾为 assistant 文本回合
    msgs = conv.messages()
    assert msgs[-1].role == "assistant"
    assert "文件内容已读取" in msgs[-1].content
    # 历史含工具调用回合与工具结果回合
    roles = [m.role for m in msgs]
    assert "tool" in roles


async def test_single_turn_cap_ac9():
    """请求#2 仍 yield 工具调用 → 只执行一次工具，不发起第二轮（AC9）。"""
    conv = Conversation()
    conv.add_user("两步任务")
    script1 = [
        StreamEvent(
            tool_calls=[ToolCall(id="t1", name="bash", input='{"command":"echo a"}')]
        ),
        StreamEvent(done=True),
    ]
    # 请求#2 又请求工具调用（应被忽略，单轮上限）
    script2 = [
        StreamEvent(
            tool_calls=[ToolCall(id="t2", name="bash", input='{"command":"echo b"}')]
        ),
        StreamEvent(text="done"),
        StreamEvent(done=True),
    ]
    provider = FakeProvider([script1, script2])
    # 用 fake 工具替换 bash 以计数执行次数
    call_count = {"n": 0}

    class CountingBash:
        def name(self) -> str:
            return "bash"

        def description(self) -> str:
            return "bash"

        def parameters(self) -> dict[str, Any]:
            return {"type": "object", "properties": {}}

        async def execute(self, args: str):
            from furflycode.tool import Result

            call_count["n"] += 1
            return Result(content=f"exec#{call_count['n']}")

    from furflycode.tool import Registry

    reg = Registry()
    reg.register(CountingBash())
    agent = Agent(provider, reg)

    events = await _events_async(agent, conv)

    # 只执行了一次 bash（请求#1 的 t1）；请求#2 的 t2 被忽略
    assert call_count["n"] == 1
    tool_ends = [e for e in events if e.tool is not None and e.tool.phase == Phase.END]
    assert len(tool_ends) == 1
    # 最终 done 仍发出
    assert events[-1].done
