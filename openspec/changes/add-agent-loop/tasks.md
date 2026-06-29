# Implementation Tasks

按依赖自底向上：叶子数据结构 → provider → agent 核心 → plan mode → tui → cli 接线 → 测试 → 验收。引用 spec（`specs/agent-loop`、`specs/tool-system`）与 design（`design.md` D1–D8）。

## 1. 基础数据结构与配置（叶子改动）

- [ ] 1.1 在 `src/furflycode/message.py` 新增 `Usage` dataclass（`input_tokens`/`output_tokens`/`cache_read_tokens`/`cache_creation_tokens`，均可选 int），给 `StreamEvent` 加 `usage: Usage | None = None` 字段。
- [ ] 1.2 在 `src/furflycode/tool/__init__.py` 给 `BaseTool` 加 `is_read_only() -> bool` 虚方法（默认 `False`）；标记仅 agent 内部用，不进 `ToolDefinition`。
- [ ] 1.3 6 个内置工具各自 override `is_read_only()`：`read_file`/`glob_tool`/`grep_tool` 返回 `True`，`write_file`/`edit_file`/`bash` 返回 `False`。
- [ ] 1.4 在 `src/furflycode/config.py` 给 `Config` 加 `max_iterations: int = 20`，`_from_dict` 从 YAML 顶层读取（缺失用默认）。

## 2. Provider 层 token 用量回传

- [ ] 2.1 更新 `src/furflycode/llm/__init__.py` 的 `Provider.stream` docstring 契约：SHOULD 在 done 前产出一次 `StreamEvent(usage=...)`（尽力而为）。
- [ ] 2.2 `src/furflycode/llm/anthropic_provider.py`：从 `final_message.usage` 取 input/output/cache tokens，在 done 前 `yield StreamEvent(usage=...)`。
- [ ] 2.3 `src/furflycode/llm/openai_provider.py`：开 `stream_options={"include_usage": True}`，从末 chunk 聚合 usage 并 `yield StreamEvent(usage=...)`；端点不支持时 usage 为 None 不崩。

## 3. Agent 核心循环重构

- [ ] 3.1 在 `src/furflycode/agent/__init__.py` 扩展事件结构：新增 `RoundEvent(iteration, has_tool_calls, usage)`，给 `Event` 加 `round: RoundEvent | None = None` 与 `done_reason: str = "normal"` 字段（保留 text/tool/done/err）。
- [ ] 3.2 抽内部 helper `_collect_round(conv, defs) -> AsyncIterator[Event]`：在 `async for ev in provider.stream(...)` 内既 `yield Event(text=...)` 实时推送、又累积 `text_buf`/`calls`/`usage`（D4 双路收集）。
- [ ] 3.3 把 `Agent.run` 从两段串联重构成 `while iteration < max_iterations` 循环（D1）：每轮 `_collect_round` → 无 calls 则 `add_assistant` + `done(normal)` → 有则 `add_assistant_with_tool_calls` → 执行 → `add_tool_results` → 下一轮。
- [ ] 3.4 `Agent.__init__` 加 `max_iterations: int = 20` 参数。
- [ ] 3.5 实现停止条件（D2）：迭代上限（落占位提示 + `done_reason="max_iterations"`）、连续 ≥2 轮全未知工具早停（`done_reason="unknown_tools"`）、流出错（既有）、用户取消（`CancelledError` 冒出不吞）。
- [ ] 3.6 实现多工具安全分批（D5）：read_only 组 `asyncio.gather` 并发、side_effect 组按序串行；每组工具仍发 `ToolEvent(START/END)`。
- [ ] 3.7 每轮流末发 `Event(round=RoundEvent(iteration, has_tool_calls, usage))`。

## 4. Plan Mode

- [ ] 4.1 在 `src/furflycode/tool/__init__.py` 的 `Registry` 加 `definitions_read_only()`，只导出 `is_read_only()` 为真的工具定义。
- [ ] 4.2 `Agent` 支持 plan 模式：按会话级模式（full/plan）选 defs 子集，plan 模式只给只读工具。
- [ ] 4.3 在 `src/furflycode/tui/app.py` 加会话级 plan 状态 + `/plan`、`/do` 命令路由（切状态、清输入框、不入 conv）。
- [ ] 4.4 plan 模式下界面状态栏显示 `PLAN MODE` 提示，与 full 模式可区分。

## 5. TUI 事件消费与可取消

- [ ] 5.1 `src/furflycode/tui/stream.py` 的 `_dispatch` 处理新 `round` 事件（更新用量/轮次显示）与 `done_reason`（区分 normal/max_iterations/unknown_tools 收尾文案）。
- [ ] 5.2 `src/furflycode/tui/app.py` 绑定 Esc：循环中（STREAMING）按 Esc cancel `_stream_task` 并复位 IDLE（区别于 Ctrl+C 退出）。
- [ ] 5.3 复用既有 `cur_reply` 在工具 START 时提交并清空的逻辑，支持多轮工具行连续渲染不交错。

## 6. cli 接线

- [ ] 6.1 `src/furflycode/cli.py` 把 `config.max_iterations` 传入 `Agent` 构造；保持 provider/registry 既有装配。

## 7. 测试

- [ ] 7.1 单测：Agent 多轮 ReAct 循环（mock provider 返回多轮 tool_calls 后无 calls，断言 conv 末尾序列与 `registry.execute` 调用次数）。
- [ ] 7.2 单测：各停止条件——迭代上限（`max_iterations=2`，断言 `done_reason=max_iterations` 与占位提示）、连续未知工具早停、流出错即止。
- [ ] 7.3 单测：双路收集（文本增量实时 yield 且 `text_buf` 完整）。
- [ ] 7.4 单测：安全分批（2 个只读工具并发用时 < 串行和；2 个副作用工具串行）。
- [ ] 7.5 单测：`is_read_only()` 6 工具分级正确；`definitions_read_only()` 只返 3 个。
- [ ] 7.6 单测：Plan Mode 下 defs 只含只读工具；`/do` 后恢复全量。
- [ ] 7.7 单测：Usage 回传（Anthropic `final_message.usage` 取值；OpenAI 端点无 usage 时降级 None 不崩）。
- [ ] 7.8 集成测：端到端多步工具任务一次提交内完成（`read_file`×2 → 综合答复）。

## 8. 验收

- [ ] 8.1 `uv run ruff check src/ tests/` 与 `uv run ruff format --check src/ tests/` 通过。
- [ ] 8.2 `uv run mypy src/` 通过（0 错误）。
- [ ] 8.3 `uv run pytest` 全过（忽略 Windows unclosed transport 噪声）。
- [ ] 8.4 `openspec validate add-agent-loop --type change` 通过；手动跑一次 TUI 多步工具任务确认自主循环、迭代上限提示与 Esc 取消。
