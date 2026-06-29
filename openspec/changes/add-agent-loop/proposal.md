## Why

tool-system 让模型能调用工具，但编排层是硬编码的「单轮闭环」：请求 → 工具 → 续答，然后就停（`tool-system` spec 当前强制本轮在最终答复后结束、禁止第二轮工具执行）。结果是模型每做一步就得用户重新催一次，无法自主完成需要多步工具协作的任务。本次变更给 FurflyCode 装上 ReAct 式 Agent Loop，让模型自主「想 → 调工具 → 看结果 → 调整」直到任务完成，从被动应答升级为能自主干活的 Agent。

## What Changes

- 把 `agent/__init__.py` 的两段硬编码串联（请求#1+执行+回灌 + 请求#2续答）重构成 `while` 循环的 ReAct 编排：每轮调 LLM → 收集工具调用 → 执行 → 结果回灌 → 下一轮，直到模型不再请求工具。
- 覆盖全部停止条件：模型本轮不再请求工具（正常完成）、达到迭代上限（兜底安全网）、用户取消（cancel 流式 task）、连续调到未知工具、流出错。迭代上限为可配默认值。
- 扩展异步事件流：在既有 text / tool / done / err 之外，新增「一轮 LLM 调用完成」「整个循环结束」「Token 用量更新」事件，Agent 与 TUI 彻底解耦。
- 流式收集器走双路：实时把文本增量推给界面，同时攒出完整响应供循环判断「是否还要继续」。
- 一次返回多个工具调用时按安全性分批：只读工具并发跑，有副作用的工具串行跑。在 `BaseTool` 增加只读/副作用标记，6 个内置工具各自声明。
- **Plan Mode 两段式**：`/plan` 切到只读工具子集让模型先出计划，`/do` 切回全工具执行。
- 在 `Config` 增加 `max_iterations` 配置位（兜底安全网）。
- 修改 `tool-system` 的「结果回灌与单轮闭环」Requirement：从「本轮 MUST 在最终答复后结束、禁止第二轮工具执行」改为「ReAct 多轮循环、受迭代上限约束」。
- 本次变更**不做**权限系统、上下文压缩、用户交互式确认——留给后续。

## Capabilities

### New Capabilities

- `agent-loop`: ReAct 自主循环编排——循环驱动、停止条件、事件流扩展（轮次完成 / 循环结束 / Token 用量）、流式双路收集、多工具调用安全分批、Plan Mode 两段式。

### Modified Capabilities

- `tool-system`: 「结果回灌与单轮闭环」Requirement 改为「结果回灌与 ReAct 循环」——允许连环工具调用、受迭代上限约束；原「单轮上限——不发起第二轮工具执行」Scenario 反转为「连环调用受迭代上限约束」。

## Impact

- `src/furflycode/agent/__init__.py`：核心重构，两段串联 → `while` 循环；`Event`/`ToolEvent` 扩展轮次与 usage 字段；`Agent` 构造接收 `max_iterations` 等参数。
- `src/furflycode/message.py`：`StreamEvent` 增加可选 usage 字段。
- `src/furflycode/tool/__init__.py`：`BaseTool` 增加只读/副作用标记，6 个工具各自声明；`Registry` 增加按安全性筛选/分批执行辅助。
- `src/furflycode/llm/__init__.py` + `anthropic_provider.py` + `openai_provider.py`：`Provider.stream` 契约补充可选 usage 产出；两适配器从 `final_message.usage` / 聚合 chunk usage 取值。
- `src/furflycode/config.py`：`Config` 增加 `max_iterations` 字段与加载。
- `src/furflycode/tui/stream.py` + `app.py`：消费新事件类型（轮次完成 / usage / 循环结束）；`/plan`、`/do` 命令路由；Plan Mode 状态与工具子集切换；循环中主动取消（如 Esc）。
- `src/furflycode/cli.py`：把 `max_iterations` 传入 `Agent`。
- 测试：新增 agent-loop 多轮循环、各停止条件、安全分批、Plan Mode 的单测与集成测。
