"""agent 包单测 — fake provider 驱动 ReAct 自主循环。"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

from furflycode.agent import Agent, Event, Phase
from furflycode.conversation import Conversation
from furflycode.message import StreamEvent, ToolCall, Usage
from furflycode.tool import (
    BaseTool,
    Registry,
    Result,
    ToolDefinition,
    new_default_registry,
)


class FakeProvider:
    """按脚本分轮吐 StreamEvent 的假 provider；记录每轮收到的 tools 列表。"""

    def __init__(self, scripts: list[list[StreamEvent]]) -> None:
        self._scripts = list(scripts)
        self._call_count = 0
        self.tools_seen: list[list[ToolDefinition]] = []

    @property
    def name(self) -> str:
        return "fake"

    @property
    def model(self) -> str:
        return "fake-model"

    @property
    def call_count(self) -> int:
        return self._call_count

    async def stream(
        self, msgs: list[Any], tools: list[ToolDefinition]
    ) -> AsyncIterator[StreamEvent]:
        self.tools_seen.append(list(tools))
        script = self._scripts[self._call_count]
        self._call_count += 1
        for ev in script:
            yield ev


async def _events(agent: Agent, conv: Conversation) -> list[Event]:
    """在事件循环中收集 agent.run 产出的全部 Event。"""
    out: list[Event] = []
    async for ev in agent.run(conv):
        out.append(ev)
    return out


class CountingTool(BaseTool):
    """计数 + 可配只读 + 可配延迟 + 记录 start/end 时间戳的假工具。"""

    def __init__(
        self, name: str = "fake", read_only: bool = False, delay: float = 0.0
    ) -> None:
        self._name = name
        self._read_only = read_only
        self._delay = delay
        self.calls = 0
        self.starts: list[float] = []
        self.ends: list[float] = []

    def name(self) -> str:
        return self._name

    def description(self) -> str:
        return "fake"

    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    def is_read_only(self) -> bool:
        return self._read_only

    async def run(self, args: dict[str, Any]) -> Result:
        self.calls += 1
        self.starts.append(time.monotonic())
        if self._delay:
            await asyncio.sleep(self._delay)
        self.ends.append(time.monotonic())
        return Result(content=f"{self._name}#{self.calls}")


# ────────────── 多轮 ReAct 循环 ──────────────


async def test_multi_round_react_loop():
    """两轮工具调用后给最终文本：conv 末尾序列 + 执行次数正确。"""
    conv = Conversation()
    conv.add_user("读 a 与 b 并综合")
    s1 = [
        StreamEvent(tool_calls=[ToolCall(id="t1", name="ro", input="{}")]),
        StreamEvent(done=True),
    ]
    s2 = [
        StreamEvent(tool_calls=[ToolCall(id="t2", name="ro", input="{}")]),
        StreamEvent(done=True),
    ]
    s3 = [StreamEvent(text="综合完毕"), StreamEvent(done=True)]
    provider = FakeProvider([s1, s2, s3])
    reg = Registry()
    tool = CountingTool(name="ro", read_only=True)
    reg.register(tool)
    agent = Agent(provider, reg)

    events = await _events(agent, conv)

    assert tool.calls == 2  # 两轮各一次
    # 末尾序列：assistant(calls) → tool → assistant(calls) → tool → assistant(final)
    msgs = conv.messages()
    assert [m.role for m in msgs[-5:]] == [
        "assistant",
        "tool",
        "assistant",
        "tool",
        "assistant",
    ]
    assert "综合完毕" in msgs[-1].content
    # 工具 START/END 各 2 次
    starts = [e for e in events if e.tool and e.tool.phase == Phase.START]
    ends = [e for e in events if e.tool and e.tool.phase == Phase.END]
    assert len(starts) == 2 and len(ends) == 2
    # 正常完成 + 3 个轮次事件
    assert events[-1].done and events[-1].done_reason == "normal"
    rounds = [e for e in events if e.round is not None]
    assert [r.round.iteration for r in rounds] == [1, 2, 3]
    assert rounds[0].round.has_tool_calls is True
    assert rounds[2].round.has_tool_calls is False


# ────────────── 停止条件 ──────────────


async def test_stop_max_iterations():
    """迭代上限兜底：max_iterations=2，模型持续请求工具 → 2 轮后停。"""
    conv = Conversation()
    conv.add_user("无限调工具")
    s = [
        StreamEvent(tool_calls=[ToolCall(id="t", name="ro", input="{}")]),
        StreamEvent(done=True),
    ]
    provider = FakeProvider([s, s, s])
    reg = Registry()
    reg.register(CountingTool(name="ro", read_only=True))
    agent = Agent(provider, reg, max_iterations=2)

    events = await _events(agent, conv)

    assert events[-1].done and events[-1].done_reason == "max_iterations"
    assert "迭代上限" in conv.messages()[-1].content
    assert provider.call_count == 2


async def test_stop_unknown_tools():
    """连续 2 轮全未知工具 → 早停。"""
    conv = Conversation()
    conv.add_user("调不存在的工具")
    s = [
        StreamEvent(tool_calls=[ToolCall(id="t", name="nope", input="{}")]),
        StreamEvent(done=True),
    ]
    provider = FakeProvider([s, s, s])
    reg = new_default_registry()  # 没有 "nope"
    agent = Agent(provider, reg, max_iterations=10)

    events = await _events(agent, conv)

    assert events[-1].done and events[-1].done_reason == "unknown_tools"
    assert provider.call_count == 2


async def test_stop_stream_error():
    """provider 流出错 → 即时停止，产出 err 事件，无 done。"""
    conv = Conversation()
    conv.add_user("触发错误")
    boom = RuntimeError("boom")
    provider = FakeProvider([[StreamEvent(text="部分"), StreamEvent(err=boom)]])
    reg = Registry()
    agent = Agent(provider, reg)

    events = await _events(agent, conv)

    errs = [e for e in events if e.err is not None]
    assert len(errs) == 1
    assert events[-1].done is False


# ────────────── 双路收集 ──────────────


async def test_dual_path_collection():
    """文本增量实时 yield，且完整累积进最终 assistant 回合。"""
    conv = Conversation()
    conv.add_user("x")
    s = [
        StreamEvent(text="al"),
        StreamEvent(text="pha"),
        StreamEvent(text=" beta"),
        StreamEvent(done=True),
    ]
    provider = FakeProvider([s])
    reg = Registry()
    agent = Agent(provider, reg)

    events = await _events(agent, conv)

    assert [e.text for e in events if e.text] == ["al", "pha", " beta"]
    assert conv.messages()[-1].content == "alpha beta"


# ────────────── 多工具安全分批 ──────────────


async def test_batching_side_effect_serial():
    """两个副作用工具串行：t2 在 t1 结束后才开始。"""
    conv = Conversation()
    conv.add_user("x")
    call = [
        ToolCall(id="t1", name="se1", input="{}"),
        ToolCall(id="t2", name="se2", input="{}"),
    ]
    provider = FakeProvider([[StreamEvent(tool_calls=call), StreamEvent(done=True)]])
    reg = Registry()
    t1 = CountingTool(name="se1", read_only=False, delay=0.1)
    t2 = CountingTool(name="se2", read_only=False, delay=0.1)
    reg.register(t1)
    reg.register(t2)
    agent = Agent(provider, reg, max_iterations=1)

    await _events(agent, conv)

    assert t2.starts[0] >= t1.ends[0] - 0.02  # 串行：t2 晚于 t1 结束


async def test_batching_read_only_concurrent():
    """两个只读工具并发：t2 在 t1 结束前就开始（重叠）。"""
    conv = Conversation()
    conv.add_user("x")
    call = [
        ToolCall(id="t1", name="ro1", input="{}"),
        ToolCall(id="t2", name="ro2", input="{}"),
    ]
    provider = FakeProvider([[StreamEvent(tool_calls=call), StreamEvent(done=True)]])
    reg = Registry()
    t1 = CountingTool(name="ro1", read_only=True, delay=0.1)
    t2 = CountingTool(name="ro2", read_only=True, delay=0.1)
    reg.register(t1)
    reg.register(t2)
    agent = Agent(provider, reg, max_iterations=1)

    await _events(agent, conv)

    assert t2.starts[0] < t1.ends[0]  # 并发：重叠


# ────────────── Plan Mode ──────────────


async def test_plan_mode_restricts_to_read_only():
    """plan_mode=True：传给 provider 的 tools 只含只读工具。"""
    conv = Conversation()
    conv.add_user("规划")
    provider = FakeProvider([[StreamEvent(text="计划..."), StreamEvent(done=True)]])
    reg = new_default_registry()
    agent = Agent(provider, reg, plan_mode=True)

    await _events(agent, conv)

    names = [t.name for t in provider.tools_seen[0]]
    assert set(names) == {"read_file", "glob", "grep"}
    assert "write_file" not in names and "bash" not in names


async def test_full_mode_has_all_tools():
    """plan_mode=False（默认）：全工具。"""
    conv = Conversation()
    conv.add_user("x")
    provider = FakeProvider([[StreamEvent(text="ok"), StreamEvent(done=True)]])
    reg = new_default_registry()
    agent = Agent(provider, reg)

    await _events(agent, conv)

    names = [t.name for t in provider.tools_seen[0]]
    assert len(names) == 6
    assert "bash" in names and "write_file" in names


# ────────────── Usage 回传 ──────────────


async def test_usage_propagated_to_round_event():
    """provider 产出 usage → round 事件携带。"""
    conv = Conversation()
    conv.add_user("x")
    u = Usage(input_tokens=100, output_tokens=20, cache_read_tokens=5)
    provider = FakeProvider(
        [[StreamEvent(text="hi"), StreamEvent(usage=u), StreamEvent(done=True)]]
    )
    reg = Registry()
    agent = Agent(provider, reg)

    events = await _events(agent, conv)

    rounds = [e for e in events if e.round is not None]
    assert len(rounds) == 1
    ru = rounds[0].round.usage
    assert ru is not None
    assert ru.input_tokens == 100
    assert ru.output_tokens == 20


async def test_usage_none_when_absent():
    """provider 不产出 usage → round.usage 为 None，不崩。"""
    conv = Conversation()
    conv.add_user("x")
    provider = FakeProvider([[StreamEvent(text="hi"), StreamEvent(done=True)]])
    reg = Registry()
    agent = Agent(provider, reg)

    events = await _events(agent, conv)

    rounds = [e for e in events if e.round is not None]
    assert len(rounds) == 1
    assert rounds[0].round.usage is None


# ────────────── 端到端多步（真实 read_file） ──────────────


async def test_end_to_end_multi_step_read(tmp_path):
    """真实 read_file×2 → 综合答复，一次提交内完成。"""
    (tmp_path / "a.txt").write_text("内容A", encoding="utf-8")
    (tmp_path / "b.txt").write_text("内容B", encoding="utf-8")
    conv = Conversation()
    conv.add_user("读 a 与 b 并综合")
    pa = json.dumps({"path": str(tmp_path / "a.txt")})
    pb = json.dumps({"path": str(tmp_path / "b.txt")})
    s1 = [
        StreamEvent(tool_calls=[ToolCall(id="t1", name="read_file", input=pa)]),
        StreamEvent(done=True),
    ]
    s2 = [
        StreamEvent(tool_calls=[ToolCall(id="t2", name="read_file", input=pb)]),
        StreamEvent(done=True),
    ]
    s3 = [StreamEvent(text="A 与 B 已综合"), StreamEvent(done=True)]
    provider = FakeProvider([s1, s2, s3])
    reg = new_default_registry()
    agent = Agent(provider, reg)

    events = await _events(agent, conv)

    tool_results = [m for m in conv.messages() if m.role == "tool"]
    assert len(tool_results) == 2
    assert "内容A" in tool_results[0].tool_results[0].content
    assert "内容B" in tool_results[1].tool_results[0].content
    assert "A 与 B 已综合" in conv.messages()[-1].content
    assert events[-1].done and events[-1].done_reason == "normal"
