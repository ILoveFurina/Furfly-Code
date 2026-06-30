"""agent 包 — ReAct 自主循环编排。

每轮：调 provider.stream 收集文本/工具调用/usage → 若无工具调用则正常结束；
若有则按安全性分批执行（只读并发、有副作用串行）→ 结果回灌 Conversation → 下一轮。
停止条件：正常完成、迭代上限兜底、连续未知工具、流出错、用户取消。
对外吐 Event async generator 供 TUI 渲染。只依赖 llm、tool、conversation，协议无关。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum

from furflycode.context import SessionContext
from furflycode.conversation import Conversation
from furflycode.llm import Provider
from furflycode.message import ROLE_USER, Message, ToolCall, ToolResult, Usage
from furflycode.tool import DEFAULT_TIMEOUT, Registry, ToolDefinition

# 这里的 Event 都是面向 TUI 的数据类型；yield 出去的都给前端消费。

# 连续全未知工具的早停阈值（兜底，防模型陷入幻觉调用死循环）。
_UNKNOWN_TOOL_STREAK_LIMIT = 2

# CONTEXT_GROWTH 触发的消息深度阈值（user/assistant/tool 回合数，零依赖协议无关）。
_CONTEXT_GROWTH_THRESHOLD = 8

# TASK_BOUNDARY 触发的模式关键词（用户消息含任一即触发）。
_TASK_BOUNDARY_KEYWORDS = ("/plan", "/do")


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
class RoundEvent:
    """一轮 LLM 调用完成（供 TUI 显示轮次与用量）。

    属性：
        iteration: 轮次号（从 1 起）。
        has_tool_calls: 本轮模型是否请求了工具调用。
        usage: 本轮 token 用量（端点不支持则为 None）。
    """

    iteration: int
    has_tool_calls: bool
    usage: Usage | None = None


@dataclass
class Event:
    """ReAct 循环对外事件流元素，TUI 据非空字段分派渲染。

    属性：
        text: 文本增量（preamble 或最终答复）。
        tool: 工具调用开始/结束。
        round: 一轮 LLM 调用完成（含轮次与用量）。
        done: 整个循环结束。
        done_reason: 结束原因（normal / max_iterations / unknown_tools）。
        err: 出错（与 done 互斥）。
    """

    text: str = ""
    tool: ToolEvent | None = None
    round: RoundEvent | None = None
    done: bool = False
    done_reason: str = "normal"
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
    """持有 provider 与注册中心，执行 ReAct 自主循环。"""

    def __init__(
        self,
        provider: Provider,
        registry: Registry,
        max_iterations: int = 20,
        plan_mode: bool = False,
        session_context: SessionContext | None = None,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._max_iterations = max_iterations
        self._plan_mode = plan_mode
        self._session_context = session_context
        # 事件驱动注入的已触发标记（同一事件不重复触发，D5）。
        self._context_growth_triggered = False
        self._task_boundary_triggered = False
        # 缓存可观测性：首轮记录 cache_creation，供后续轮断言 read ≈ 首轮 creation。
        self._first_round_creation: int | None = None
        # 可观测性断言结果（供测试钩子读取，不阻断正常运行）。
        self.cache_observations: list[dict[str, object]] = []

    async def run(self, conv: Conversation) -> AsyncIterator[Event]:
        """执行 ReAct 自主循环，async generator 吐出事件流。

        调用方 cancel() 该 task 即终止（CancelledError 冒出不吞）；
        工具执行经 asyncio.wait_for 受 DEFAULT_TIMEOUT 约束。
        """
        defs = (
            self._registry.definitions_read_only()
            if self._plan_mode
            else self._registry.definitions()
        )
        iteration = 0
        unknown_streak = 0

        while iteration < self._max_iterations:
            iteration += 1

            # ─── 事件驱动注入：本轮请求前判定触发，<system_reminder> 追加 conv 末尾 ───
            injection = self._maybe_inject_reminder(conv)
            if injection:
                conv.add_user(injection)

            # ─── 双路收集一轮：实时推文本给 TUI，累积 calls/usage 供判断 ───
            calls: list[ToolCall] = []
            usage: list[Usage | None] = [None]
            text_buf = ""
            round_err: Exception | None = None
            async for ev in self._collect_round(conv, defs, calls, usage):
                yield ev  # 实时转发（text / err）
                if ev.err is not None:
                    round_err = ev.err
                if ev.text:
                    text_buf += ev.text
            if round_err is not None:
                # 流出错：err 已转发，停止循环（不产出 done）。
                return

            # ─── 缓存可观测性断言（D8，不阻断运行）───
            self._observe_cache(usage[0], iteration)

            # ─── 一轮LLM调用完成事件 ───
            yield Event(
                round=RoundEvent(
                    iteration=iteration,
                    has_tool_calls=bool(calls),
                    usage=usage[0],
                )
            )

            if not calls:
                # 模型本轮不再请求工具 → 正常完成。
                conv.add_assistant(text_buf)
                yield Event(done=True, done_reason="normal")
                return

            # ─── 有工具调用：落 assistant 工具调用回合 ───
            conv.add_assistant_with_tool_calls(text_buf, calls)

            # ─── 安全分批执行 + 收集结果（只读并发、有副作用串行） ───
            read_only = [c for c in calls if self._is_read_only(c.name)]
            side_effect = [c for c in calls if not self._is_read_only(c.name)]
            result_by_id: dict[str, ToolResult] = {}

            if read_only:
                for c in read_only:
                    yield Event(
                        tool=ToolEvent(
                            name=c.name,
                            args=_preview_args(c.input),
                            phase=Phase.START,
                        )
                    )
                rs = await asyncio.gather(
                    *(
                        self._registry.execute(c.name, c.input, timeout=DEFAULT_TIMEOUT)
                        for c in read_only
                    )
                )
                for c, r in zip(read_only, rs):
                    yield Event(
                        tool=ToolEvent(
                            name=c.name,
                            phase=Phase.END,
                            result=r.content,
                            is_error=r.is_error,
                        )
                    )
                    result_by_id[c.id] = ToolResult(
                        tool_call_id=c.id,
                        content=r.content,
                        is_error=r.is_error,
                    )

            for c in side_effect:
                yield Event(
                    tool=ToolEvent(
                        name=c.name,
                        args=_preview_args(c.input),
                        phase=Phase.START,
                    )
                )
                r = await self._registry.execute(
                    c.name, c.input, timeout=DEFAULT_TIMEOUT
                )
                yield Event(
                    tool=ToolEvent(
                        name=c.name,
                        phase=Phase.END,
                        result=r.content,
                        is_error=r.is_error,
                    )
                )
                result_by_id[c.id] = ToolResult(
                    tool_call_id=c.id,
                    content=r.content,
                    is_error=r.is_error,
                )

            # ─── 结果按原序回灌 ───
            conv.add_tool_results([result_by_id[c.id] for c in calls])

            # ─── 连续全未知工具早停 ───
            all_unknown = all(self._registry.get(c.name) is None for c in calls)
            if all_unknown:
                unknown_streak += 1
                if unknown_streak >= _UNKNOWN_TOOL_STREAK_LIMIT:
                    conv.add_assistant("（连续多轮调用未知工具，已停止循环）")
                    yield Event(done=True, done_reason="unknown_tools")
                    return
            else:
                unknown_streak = 0

            # 继续下一轮

        # ─── 迭代上限兜底（非静默） ───
        conv.add_assistant(
            f'（已达到迭代上限 {self._max_iterations}，可发送"继续"推进）'
        )
        yield Event(done=True, done_reason="max_iterations")

    async def _collect_round(
        self,
        conv: Conversation,
        defs: list[ToolDefinition],
        calls: list[ToolCall],
        usage_out: list[Usage | None],
    ) -> AsyncIterator[Event]:
        """双路收集一轮流式：实时 yield 文本增量，累积 calls 与 usage 供循环判断。

        calls：追加模型请求的工具调用。
        usage_out：单元素列表，写入本轮 usage（可 None）。
        出错时 yield Event(err=...) 后返回；done 时正常返回。
        不向 TUI 暴露原始 tool_calls。
        """
        async for ev in self._provider.stream(self._build_messages(conv), defs):
            if ev.err is not None:
                yield Event(err=ev.err)
                return
            if ev.text:
                yield Event(text=ev.text)
            if ev.tool_calls:
                calls.extend(ev.tool_calls)
            if ev.usage is not None:
                usage_out[0] = ev.usage
            if ev.done:
                return

    def _is_read_only(self, name: str) -> bool:
        """工具是否只读；未知工具视为有副作用（保守，归副作用串行组）。"""
        tool = self._registry.get(name)
        return tool is not None and tool.is_read_only()

    def _build_messages(self, conv: Conversation) -> list[Message]:
        """组装发往 provider 的 messages：会话上下文块在开头 + 对话历史 + 末尾事件注入。

        环境信息与 FURFLY.md 内容（来自 SessionContext）作为 user 角色消息置于
        messages 开头，不进 system 缓存区；conversation 层保持纯 user/assistant/tool。
        事件触发的 <system_reminder> 注入追加于末尾（绝不中间插入，D5）。
        无 SessionContext 时直接返回对话历史（向后兼容）。
        """
        history = conv.messages()
        if self._session_context is None:
            return history
        prefix_msgs: list[Message] = []
        ctx = self._session_context
        # 环境信息与 FURFLY.md 合并为一条 user 消息置于开头（同在 messages 开头块）。
        blocks = [ctx.env_info_block, ctx.furfly_md_block]
        preamble = "\n\n".join(b for b in blocks if b)
        if preamble:
            prefix_msgs.append(Message(role=ROLE_USER, content=preamble))
        return prefix_msgs + history

    def _maybe_inject_reminder(self, conv: Conversation) -> str:
        """判定事件触发条件，返回要追加的 <system_reminder> 内容；无触发返回空串。

        两触发条件（D5）：CONTEXT_GROWTH（消息深度 ≥ 阈值，基于消息条数零依赖）、
        TASK_BOUNDARY（用户消息含模式关键词）。同一事件不重复触发。
        砍掉 MODE_DEVIATION——Plan Mode 工具子集隔离已物理阻断有害偏离。
        """
        history = conv.messages()
        injection: list[str] = []
        # CONTEXT_GROWTH：消息深度达阈值且未触发过。
        if (
            not self._context_growth_triggered
            and len(history) >= _CONTEXT_GROWTH_THRESHOLD
        ):
            self._context_growth_triggered = True
            injection.append(
                "会话已较长，请确认仍紧扣当前任务目标；若用户已转换话题，"
                "以最新需求为准。"
            )
        # TASK_BOUNDARY：最近一条用户消息含模式关键词且未触发过。
        if not self._task_boundary_triggered:
            last_user = next(
                (m for m in reversed(history) if m.role == ROLE_USER and m.content),
                None,
            )
            if last_user and any(
                kw in last_user.content for kw in _TASK_BOUNDARY_KEYWORDS
            ):
                self._task_boundary_triggered = True
                injection.append(
                    "检测到模式切换关键词。Plan 模式下只输出计划、不直接修改文件；"
                    "Do 模式下恢复全工具执行。"
                )
        if not injection:
            return ""
        body = "\n".join(injection)
        return f"<system_reminder>\n{body}\n</system_reminder>"

    def _observe_cache(self, usage: Usage | None, iteration: int) -> None:
        """缓存可观测性断言（D8）：记录首轮 creation，后续轮检查 read 漂移。

        不阻断正常运行——断言结果记入 self.cache_observations 供测试钩子读取；
        实测漂移 >2% 视为动静分离漏点信号。OpenAI 路径降级判 cached_tokens > 0。
        """
        if usage is None:
            return
        creation = usage.cache_creation_tokens
        read = usage.cache_read_tokens
        # 首轮记录 creation 基准（Anthropic 首轮 creation>0, read=0）。
        if iteration == 1 and creation is not None and creation > 0:
            self._first_round_creation = creation
        # 后续轮：若已有首轮基准，检查 read 是否接近首轮 creation（±2%）。
        if (
            iteration > 1
            and self._first_round_creation is not None
            and read is not None
        ):
            baseline = self._first_round_creation
            drift = abs(read - baseline) / baseline if baseline else 0.0
            self.cache_observations.append(
                {
                    "iteration": iteration,
                    "creation": creation,
                    "read": read,
                    "baseline": baseline,
                    "drift_ratio": drift,
                    "stable": drift <= 0.02,
                }
            )
