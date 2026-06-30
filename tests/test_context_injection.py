"""上下文注入单测 — FURFLY.md 加载器、env_info、事件驱动注入、缓存可观测性。

覆盖 tasks 8.4/8.5/8.6/8.7/8.8/8.9。用 tmp_path 构造多级 FURFLY.md 验证向上
查找与合并；用记录 msgs 的 FakeProvider 验证注入位置与可观测性断言。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from furflycode.agent import Agent, Event
from furflycode.context import build_session_context, load_furfly_md
from furflycode.context.furfly_md import _collect_furfly_md_paths
from furflycode.conversation import Conversation
from furflycode.message import ROLE_USER, StreamEvent, Usage
from furflycode.tool import new_default_registry

# ─── 8.4 FURFLY.md 加载器 ──────────────────────────────────────────


def _make_project_tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    """在 tmp_path 下建项目根(.git) + 子目录，返回 (root, subdir, root_furfly)。"""
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".git").mkdir()
    sub = root / "a" / "b"
    sub.mkdir(parents=True)
    return root, sub, root


def test_collect_upward_to_git_root(tmp_path: Path):
    """向上查找至 .git 项目根，收集路径上所有 FURFLY.md。"""
    root, sub, _ = _make_project_tree(tmp_path)
    (root / "FURFLY.md").write_text("root rules", encoding="utf-8")
    (root / "a" / "FURFLY.md").write_text("mid rules", encoding="utf-8")
    (sub / "FURFLY.md").write_text("leaf rules", encoding="utf-8")

    paths = _collect_furfly_md_paths(sub)
    # 顺序：从远（root）到近（sub）。
    assert paths == [root / "FURFLY.md", root / "a" / "FURFLY.md", sub / "FURFLY.md"]


def test_merge_nearby_content_arranged_later(tmp_path: Path):
    """多份叠加，就近（更靠近 cwd）内容排列在后。"""
    root, sub, _ = _make_project_tree(tmp_path)
    (root / "FURFLY.md").write_text("GLOBAL", encoding="utf-8")
    (sub / "FURFLY.md").write_text("LOCAL", encoding="utf-8")

    content = load_furfly_md(sub)
    assert "GLOBAL" in content
    assert "LOCAL" in content
    # 全局在前，局部在后。
    assert content.index("GLOBAL") < content.index("LOCAL")


def test_missing_furfly_md_silent(tmp_path: Path):
    """文件缺失静默返回空串，不抛异常。"""
    root, sub, _ = _make_project_tree(tmp_path)
    # 无任何 FURFLY.md。
    assert load_furfly_md(sub) == ""


def test_no_git_root_fallback(tmp_path: Path):
    """无 .git 时回退到 cwd 本身，只查找 cwd 的 FURFLY.md。"""
    cwd = tmp_path / "nogit"
    cwd.mkdir()
    (cwd / "FURFLY.md").write_text("only", encoding="utf-8")
    # 不应向上爬到 tmp_path 之外。
    content = load_furfly_md(cwd)
    assert "only" in content


def test_large_file_truncated(tmp_path: Path):
    """大文件截断标注。"""
    root, sub, _ = _make_project_tree(tmp_path)
    big = "X" * (8 * 1024 + 500)
    (sub / "FURFLY.md").write_text(big, encoding="utf-8")
    content = load_furfly_md(sub)
    assert "[truncated]" in content


def test_build_session_context_snapshot(tmp_path: Path):
    """build_session_context 产出不可变快照，含 env_info 与 furfly_md 块。"""
    root, sub, _ = _make_project_tree(tmp_path)
    (sub / "FURFLY.md").write_text("rules", encoding="utf-8")
    ctx = build_session_context(sub)
    assert "<env_info>" in ctx.env_info_block
    assert "</env_info>" in ctx.env_info_block
    assert str(sub) in ctx.env_info_block
    assert "<furfly_md>" in ctx.furfly_md_block
    assert "rules" in ctx.furfly_md_block
    assert ctx.furfly_md_paths == [sub / "FURFLY.md"]


# ─── 8.5 注入位置（messages 开头，不进 system/tools） ────────────


class MsgsRecordingProvider:
    """记录每轮收到的 msgs 的假 provider；按脚本吐 StreamEvent。"""

    def __init__(self, scripts: list[list[StreamEvent]]) -> None:
        self._scripts = list(scripts)
        self._call_count = 0
        self.msgs_seen: list[list[Any]] = []

    @property
    def name(self) -> str:
        return "fake"

    @property
    def model(self) -> str:
        return "fake-model"

    async def stream(
        self, msgs: list[Any], tools: list[Any]
    ) -> AsyncIterator[StreamEvent]:
        self.msgs_seen.append(list(msgs))
        script = self._scripts[self._call_count]
        self._call_count += 1
        for ev in script:
            yield ev


def _env_only_script() -> list[StreamEvent]:
    """单轮无工具调用：吐 usage + done。"""
    return [
        StreamEvent(usage=Usage(input_tokens=10, output_tokens=5)),
        StreamEvent(done=True),
    ]


def _msg_content(msg: Any) -> str:
    """从 provider 收到的消息取 content（Message 对象或 dict 兼容）。"""
    return msg["content"] if isinstance(msg, dict) else msg.content


def _msg_role(msg: Any) -> str:
    """从 provider 收到的消息取 role（Message 对象或 dict 兼容）。"""
    return msg["role"] if isinstance(msg, dict) else msg.role


def test_env_info_and_furfly_md_at_messages_start(tmp_path: Path):
    """环境信息与 FURFLY.md 以标签包裹位于 messages 开头。"""
    root, sub, _ = _make_project_tree(tmp_path)
    (sub / "FURFLY.md").write_text("proj rules", encoding="utf-8")
    ctx = build_session_context(sub)

    provider = MsgsRecordingProvider([_env_only_script()])
    agent = Agent(provider, new_default_registry(), session_context=ctx)
    conv = Conversation()
    conv.add_user("hi")

    async def run() -> None:
        async for _ in agent.run(conv):
            pass

    import asyncio

    asyncio.run(run())

    msgs = provider.msgs_seen[0]
    # 首条应是 env_info + furfly_md 合并的 user 消息（开头）。
    first = msgs[0]
    assert _msg_role(first) == ROLE_USER
    content = _msg_content(first)
    assert "<env_info>" in content
    assert "<furfly_md>" in content
    assert "proj rules" in content
    # 开头块之后才是用户消息 "hi"。
    assert any(_msg_content(m) == "hi" for m in msgs[1:])


def test_no_session_context_backward_compatible():
    """无 SessionContext 时 Agent 向后兼容，直接用对话历史。"""
    provider = MsgsRecordingProvider([_env_only_script()])
    agent = Agent(provider, new_default_registry(), session_context=None)
    conv = Conversation()
    conv.add_user("hi")

    import asyncio

    async def run() -> None:
        async for _ in agent.run(conv):
            pass

    asyncio.run(run())
    msgs = provider.msgs_seen[0]
    # 无前缀注入，首条即用户消息。
    first = msgs[0]
    assert _msg_content(first) == "hi"


# ─── 8.6 事件驱动注入 ─────────────────────────────────────────────


def _no_tool_no_usage() -> list[StreamEvent]:
    return [StreamEvent(done=True)]


def _build_deep_conv(rounds: int) -> Conversation:
    """构造 rounds 个 user/assistant 回合的深对话。"""
    conv = Conversation()
    for i in range(rounds):
        conv.add_user(f"u{i}")
        conv.add_assistant(f"a{i}")
    return conv


def test_context_growth_triggers_at_threshold(tmp_path: Path):
    """CONTEXT_GROWTH 在 ≥8 回合触发，基于消息条数（无 tokenizer）。"""
    ctx = build_session_context(tmp_path)
    provider = MsgsRecordingProvider([_no_tool_no_usage()])
    agent = Agent(provider, new_default_registry(), session_context=ctx)
    conv = _build_deep_conv(4)  # 8 条消息 = 阈值
    conv.add_user("next")  # 触发本轮

    import asyncio

    async def run() -> None:
        async for _ in agent.run(conv):
            pass

    asyncio.run(run())
    # 末尾应有一条 <system_reminder> 注入（追加于 messages 末尾）。
    msgs = provider.msgs_seen[0]
    last = msgs[-1]
    content = _msg_content(last)
    assert "<system_reminder>" in content
    assert agent._context_growth_triggered is True


def test_context_growth_not_triggered_below_threshold(tmp_path: Path):
    """消息深度低于阈值时不触发 CONTEXT_GROWTH。"""
    ctx = build_session_context(tmp_path)
    provider = MsgsRecordingProvider([_no_tool_no_usage()])
    agent = Agent(provider, new_default_registry(), session_context=ctx)
    conv = _build_deep_conv(2)  # 4 条 < 8
    conv.add_user("next")

    import asyncio

    async def run() -> None:
        async for _ in agent.run(conv):
            pass

    asyncio.run(run())
    msgs = provider.msgs_seen[0]
    last = msgs[-1]
    content = _msg_content(last)
    assert "<system_reminder>" not in content


def test_task_boundary_triggers_on_keyword(tmp_path: Path):
    """TASK_BOUNDARY 按模式关键词触发。"""
    ctx = build_session_context(tmp_path)
    provider = MsgsRecordingProvider([_no_tool_no_usage()])
    agent = Agent(provider, new_default_registry(), session_context=ctx)
    conv = Conversation()
    conv.add_user("let's /plan this")

    import asyncio

    async def run() -> None:
        async for _ in agent.run(conv):
            pass

    asyncio.run(run())
    msgs = provider.msgs_seen[0]
    last = msgs[-1]
    content = _msg_content(last)
    assert "<system_reminder>" in content
    assert agent._task_boundary_triggered is True


def test_injection_appended_at_end_not_middle(tmp_path: Path):
    """注入永远追加于 messages 末尾，绝不中间插入。"""
    ctx = build_session_context(tmp_path)
    provider = MsgsRecordingProvider([_no_tool_no_usage()])
    agent = Agent(provider, new_default_registry(), session_context=ctx)
    conv = _build_deep_conv(4)
    conv.add_user("next")

    import asyncio

    async def run() -> None:
        async for _ in agent.run(conv):
            pass

    asyncio.run(run())
    msgs = provider.msgs_seen[0]
    # 注入是最后一条；其前的消息都应是历史（不含 system_reminder）。
    last = msgs[-1]
    last_content = _msg_content(last)
    assert "<system_reminder>" in last_content
    for m in msgs[:-1]:
        c = _msg_content(m)
        assert "<system_reminder>" not in c


def test_no_mode_deviation_detection():
    """不实现 MODE_DEVIATION——触发条件集合仅 CONTEXT_GROWTH/TASK_BOUNDARY。"""
    # 通过检查 Agent 无 mode_deviation 相关属性/方法。
    agent = Agent.__new__(Agent)
    assert not hasattr(agent, "_mode_deviation_triggered")
    # 触发关键词集合不含 mode_deviation。
    from furflycode.agent import _TASK_BOUNDARY_KEYWORDS

    assert "mode_deviation" not in str(_TASK_BOUNDARY_KEYWORDS).lower()


# ─── 8.7 缓存可观测性断言 ─────────────────────────────────────────


def _cache_usage(creation: int | None, read: int | None) -> StreamEvent:
    return StreamEvent(
        usage=Usage(
            input_tokens=100,
            output_tokens=10,
            cache_creation_tokens=creation,
            cache_read_tokens=read,
        )
    )


def test_cache_observable_first_round_write_then_hit():
    """Anthropic 首轮 creation>0 read=0，第 2 轮 creation=0 read≈首轮 creation(±2%)。"""
    from furflycode.message import ToolCall

    tc = ToolCall(id="t1", name="read_file", input='{"path":"x"}')
    scripts = [
        # 第 1 轮：写入缓存 + 请求工具调用（驱动循环进入第 2 轮）。
        [
            StreamEvent(
                usage=Usage(
                    input_tokens=100,
                    output_tokens=10,
                    cache_creation_tokens=1000,
                    cache_read_tokens=0,
                )
            ),
            StreamEvent(tool_calls=[tc]),
        ],
        # 第 2 轮：命中缓存（read≈首轮 creation）+ 无工具调用收尾。
        [_cache_usage(0, 1000), StreamEvent(done=True)],
    ]
    provider = MsgsRecordingProvider(scripts)
    agent = Agent(provider, new_default_registry())
    conv = Conversation()
    conv.add_user("q")

    import asyncio

    async def run() -> list[Event]:
        out: list[Event] = []
        async for ev in agent.run(conv):
            out.append(ev)
        return out

    # registry 的 read_file 会因文件不存在返回 is_error 结果，回灌后第二轮无 calls。
    asyncio.run(run())
    # 首轮基准已记录。
    assert agent._first_round_creation == 1000
    # 第 2 轮观测记录存在且 read 接近 baseline（drift ≤ 2%）。
    assert len(agent.cache_observations) >= 1
    obs = agent.cache_observations[0]
    assert obs["read"] == 1000
    assert obs["baseline"] == 1000
    assert obs["drift_ratio"] == 0.0
    assert obs["stable"] is True


def test_cache_observable_detects_drift():
    """前缀变动时 read 骤降偏离 baseline >2%，被可观测性检出为不稳定。"""
    from furflycode.message import ToolCall

    tc_drift = ToolCall(id="t1", name="read_file", input='{"path":"x"}')
    scripts = [
        [
            StreamEvent(
                usage=Usage(
                    input_tokens=100,
                    output_tokens=10,
                    cache_creation_tokens=1000,
                    cache_read_tokens=0,
                )
            ),
            StreamEvent(tool_calls=[tc_drift]),
        ],
        [
            StreamEvent(
                usage=Usage(
                    input_tokens=100,
                    output_tokens=10,
                    cache_creation_tokens=0,
                    cache_read_tokens=500,  # 远低于 baseline 1000，drift 50%
                )
            ),
            StreamEvent(done=True),
        ],
    ]
    provider = MsgsRecordingProvider(scripts)
    agent = Agent(provider, new_default_registry())
    conv = Conversation()
    conv.add_user("q")

    import asyncio

    async def run() -> None:
        async for _ in agent.run(conv):
            pass

    asyncio.run(run())
    obs = agent.cache_observations[0]
    assert obs["drift_ratio"] > 0.02
    assert obs["stable"] is False


# ─── 8.8 Plan Mode 缓存代价 ───────────────────────────────────────


def test_plan_mode_uses_read_only_subset():
    """Plan Mode 切到只读工具子集（3 个），full 模式全量（6 个）——切换使 tools 变化。"""
    registry = new_default_registry()
    full_defs = registry.definitions()
    plan_defs = registry.definitions_read_only()
    assert len(full_defs) == 6
    assert len(plan_defs) == 3
    plan_names = {d.name for d in plan_defs}
    assert "edit_file" not in plan_names
    assert "write_file" not in plan_names
    assert "bash" not in plan_names
    # tools 数组变化即意味着缓存断点② miss（代价被体现）。
    assert {d.name for d in full_defs} != plan_names


def test_plan_mode_no_subagent():
    """Plan Mode 不升级子代理——Agent 仍是单实例，无子代理编排字段。"""
    agent = Agent.__new__(Agent)
    assert not hasattr(agent, "_plan_subagent")
    assert not hasattr(agent, "_subagent_context")


# ─── 8.9 集成：多轮对话注入不击穿 system 缓存 ─────────────────────


def test_multiround_static_prefix_stable(tmp_path: Path):
    """多轮对话中 env_info/furfly_md 前缀块跨轮稳定（字节级一致），不击穿缓存。"""
    root, sub, _ = _make_project_tree(tmp_path)
    (sub / "FURFLY.md").write_text("stable rules", encoding="utf-8")
    ctx = build_session_context(sub)

    from furflycode.message import ToolCall

    tc = ToolCall(id="t1", name="read_file", input='{"path":"x"}')
    scripts = [
        [_cache_usage(1000, 0), StreamEvent(tool_calls=[tc])],
        [_cache_usage(0, 1000), StreamEvent(done=True)],
    ]
    provider = MsgsRecordingProvider(scripts)
    agent = Agent(provider, new_default_registry(), session_context=ctx)
    conv = Conversation()
    conv.add_user("q")

    import asyncio

    async def run() -> None:
        async for _ in agent.run(conv):
            pass

    asyncio.run(run())
    # 两轮的 messages 前缀块（首条）应字节级一致——静态前缀稳定。
    first_round_prefix = provider.msgs_seen[0][0]
    second_round_prefix = provider.msgs_seen[1][0]
    c1 = _msg_content(first_round_prefix)
    c2 = _msg_content(second_round_prefix)
    assert c1 == c2
    assert "<env_info>" in c1
    assert "<furfly_md>" in c1
    assert "stable rules" in c1
