## Context

当前 `agent/__init__.py` 是硬编码两段串联：请求#1（收文本+工具调用）→ 执行 → 回灌 → 请求#2（续答，`continue` 丢弃其工具调用以满足单轮上限）。`tool-system` spec 的「结果回灌与单轮闭环」Requirement 显式禁止第二轮工具执行。`Conversation` 已提供 `add_assistant_with_tool_calls` / `add_tool_results` 且可重复调用，多轮历史结构天然就位。`StreamEvent` 四态（text/tool_calls/done/err）无 usage；`BaseTool` 无只读/副作用标记；`Config` 无迭代上限位。TUI 的 `consume_agent_events` 只消费 Event 流到 `done`，对 Agent 内部几步不可见——Agent Loop 对它基本透明。

约束（来自既有 spec 与 API）：
- `agent/` 不得 import `anthropic`/`openai`，协议无关。
- `message.py`/`tool/` 零内部依赖、不绑 LLM 协议。
- 工具执行不外抛异常：超时/异常/未知工具一律转 `Result(is_error=True)`。
- Anthropic `_has_tool_history` 为真时关 thinking（避免签名缺失 400）——循环进入第二轮后必然含工具历史，故 thinking 仅首轮 preamble 可用，这是 API 硬约束，本次不突破。

## Goals / Non-Goals

**Goals:**
- 把两段串联重构成统一 `while` 循环的 ReAct 编排，模型自主多步工具协作直到完成。
- 覆盖全部停止条件：正常完成、迭代上限（兜底）、用户取消、连续未知工具、流出错。
- 事件流扩展：轮次完成（含 usage）/ 循环结束（含 reason）/ 文本 / 工具 / 错误，Agent 与 TUI 彻底解耦。
- 流式双路：实时推文本给 TUI，同时攒完整响应供循环判断。
- 多工具调用安全分批：只读并发、有副作用串行。
- Plan Mode 两段式：`/plan` 只读工具出计划，`/do` 全工具执行。
- `max_iterations` 可配。

**Non-Goals:**
- 权限系统、上下文压缩、用户交互式确认——留给后续。
- 突破 thinking 在工具历史下被关闭的 API 约束。
- 跨会话历史持久化（既有约束：退出即清空）。

## Decisions

### D1: 单 while 循环统一请求#1 与请求#2，消除两段割裂
把「请求#1+执行+回灌」与「请求#2续答」合并为统一循环体：每轮 stream 收集 → 无工具调用则 break（正常完成）→ 有则执行+回灌 → 下一轮。续答不过是「下一轮恰好没有工具调用」的特例。**替代方案**：外层 while 包住两段式——但单轮上限的 `continue` 丢弃逻辑与循环语义冲突（续答里的工具调用到底执不执行？），不如统一为「有 calls 就继续、无则停」。统一后 conv 变动模式每轮一致：`add_assistant_with_tool_calls(text, calls)` → 执行 → `add_tool_results(results)` → 下一轮；末轮无 calls 时 `add_assistant(text)` 收尾。

### D2: 停止条件分级，迭代上限为兜底安全网
- **正常完成**：某轮 `not calls` → `add_assistant(text)` → `Event(done=True, reason="normal")`。
- **迭代上限**：`iteration >= max_iterations` → 停，落占位提示 `（已达到迭代上限 N，可发送"继续"推进）` 并 `add_assistant` → `Event(done=True, reason="max_iterations")`。非静默截断。
- **用户取消**：调用方 cancel `_stream_task` → `CancelledError` 从 `async for` 冒出，agent 不吞，TUI 捕获后复位 IDLE。既有 `action_quit` 已 cancel；新增循环中主动取消（Esc 键，区别于 Ctrl+C 退出）。
- **连续未知工具**：连续 ≥2 轮中**所有**调用都是未知工具（`registry.get` 返回 None → `Result(is_error)`）→ 停，避免模型陷入幻觉调用死循环。单次未知仍回灌让模型自我纠正。
- **流出错**：`ev.err` → `yield Event(err=...)` → `return`（既有，保持）。

### D3: 事件流扩展——在 text/tool/done/err 外加 round，done 携带 reason
新增 `RoundEvent(iteration: int, has_tool_calls: bool, usage: Usage | None)`：每轮 stream 结束、执行工具前发出，让 TUI 可显示轮次与用量。`done` 扩展携带 `reason`（normal/max_iterations/cancelled/error）供 TUI 区分收尾。`Event` 改为：`text` / `tool` / `round` / `done` / `done_reason` / `err`，新字段均有默认值，TUI 向后兼容。**为何不独立 usage 事件**：provider 目前每轮一次性产出 usage（Anthropic 从 `final_message.usage`、OpenAI 从末 chunk），与轮次完成天然同点，并入 round 减少事件类型；若将来 provider 分段产出再拆独立事件。

### D4: 双路流式收集器——边推边攒，合于一处
抽内部 helper `_collect_round(conv, defs) -> tuple[text_buf, calls, usage, err|None]`，在 `async for ev in provider.stream(...)` 内：每收到 `ev.text` 既 `yield Event(text=ev.text)`（实时推 TUI）又 `text_buf += ev.text`（攒完整响应）；`ev.tool_calls` 累积进 `calls`；`ev.usage` 暂存；`ev.err` 即时 yield 并标记返回。两路在同一个循环里自然合一，无需双队列。**替代方案**：先攒完再推——破坏实时打字观感；两套独立消费者——复杂且易乱序。合一最优。

### D5: 多工具调用安全分批——只读并发、有副作用串行
给 `BaseTool` 加 `is_read_only() -> bool` 虚方法（默认 `False`，保守视为有副作用）。`read_file`/`glob`/`grep` 声明 `True`；`write_file`/`edit_file`/`bash` 声明 `False`（bash 即使 `echo` 也保守归副作用）。一轮的 `calls` 分两组：read_only 组 `asyncio.gather` 并发执行；side_effect 组按模型给出顺序串行。两组顺序：先并发跑 read_only，再串行跑 side_effect。**理由**：同轮多个调用是模型「同时」请求的，语义上互不依赖（依赖会拆成多轮）；read_only 无副作用可安全并发提速，side_effect 串行避免 race。**替代方案**：全部串行最简保语义——但浪费并发机会，违背「能并发的并发跑」诉求。**风险**：模型同轮先请求 side_effect 再请求依赖其结果的 read_only——但模型不会这样设计（同轮=并行意图），且结果依赖会被模型拆成多轮，可接受。

### D6: Plan Mode 会话级开关 + 工具子集过滤
Plan Mode 为会话级状态（`Literal["full","plan"]`，默认 full）。`/plan` 切到 plan → 该模式下每轮传给 provider 的 `defs` 只含 `is_read_only()` 为真的工具 → 模型只能探查不能改 → 出计划文本。`/do` 切回 full → 全工具。实现：`Registry` 加 `definitions_read_only()`，Agent 按 plan 模式选 defs 子集；TUI 状态栏在 plan 模式下显示 `PLAN MODE` 提示防漏切。**替代方案**：`/plan` 只影响下一轮——但用户常需多轮探查后出计划，会话级开关更自然；`/do` 显式切回。

### D7: token usage——StreamEvent 加可选 usage，两适配器尽力产出
`message.py` 加 `Usage` dataclass（`input_tokens`/`output_tokens`/`cache_read_tokens`/`cache_creation_tokens`，均可选）与 `StreamEvent.usage` 字段。Provider Protocol 契约补充：stream SHOULD 在 done 前产出一次 `StreamEvent(usage=...)`（尽力而为，非强制）。Anthropic 从 `final_message.usage` 取；OpenAI 开 `stream_options={"include_usage": True}` 从末 chunk 取。Agent 把 usage 包进 round 事件。**降级**：兼容端点可能不支持 usage → round 事件 `usage=None`，TUI 不崩，用量区不显示。

### D8: max_iterations 配置于 Config 顶层，默认 20
`Config` 加 `max_iterations: int = 20`（顶层，非 per-provider，因为是 agent 编排骨架行为）。`_from_dict` 读取，缺失用默认。`cli.py` 把 `config.max_iterations` 传给 `Agent`。**默认 20 理由**：多数任务 5–10 轮够，20 给足余量又防失控；可配让长任务调高。

## Risks / Trade-offs

- **[迭代上限截断长任务]** → 上限可配；到达时落明确占位提示（非静默），用户可发「继续」推进下一轮循环。
- **[连续未知工具早停误判]** → 阈值取 2（连续 2 轮全未知才停），单次未知仍回灌让模型自我纠正；阈值可在设计评审中调。
- **[read_only 并发改工具内部状态]** → 标记基于工具自身声明；read_file/glob/grep 确实只读无状态；bash 一律保守归副作用。
- **[Plan Mode 漏切回]** → `/do` 显式切回；plan 模式下状态栏显示 `PLAN MODE` 提示。
- **[OpenAI 兼容端点无 usage]** → usage 可选，缺失不崩，TUI 降级不显示用量。
- **[thinking 二轮起关闭]** → API 硬约束，不突破；首轮 preamble 可 thinking，后续轮无 thinking，spec 已认可。

## Migration Plan

纯重构 + 扩展，无数据迁移、无持久状态变更。改动面：
- `Agent.__init__` 签名加 `max_iterations` → `cli.py` 同步传参（破坏性仅限内部构造，非用户 API）。
- `Event` 加字段均有默认值 → TUI 按非空字段分派，向后兼容。
- `BaseTool` 加 `is_read_only` 虚方法有默认 → 6 个工具各自 override，非破坏。
- `StreamEvent` 加可选 `usage` → provider 向后兼容。
回滚：`git revert`，无遗留状态。

## Open Questions

- 循环中主动取消的快捷键：倾向 **Esc**（Ctrl+C 已绑退出，需区分「取消本轮循环」与「退出程序」），待实现期与 TUI 按键映射一并定。
- 连续未知工具早停阈值：倾向 **2**，可在实现期据测试反馈调。
