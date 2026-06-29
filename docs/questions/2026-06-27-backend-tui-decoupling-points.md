---
status: answered
tags: [architecture, backend, tui, decoupling]
created: 2026-06-27
answered: 2026-06-27
updated: 2026-06-29
related:
  - 2026-06-27-provider-protocol-and-runtime-checkable.md
  - 2026-06-27-protocol-vs-abc-design-choice.md
---

# 不关注 GUI 逻辑，但想正确处理后端逻辑，应该关注什么对接点？

## 背景

想专注做后端（LLM 协议层、会话层、配置层、工具系统、agent 编排），不想被 TUI 的渲染、状态机、事件循环分心。
但又必须知道：哪些契约是 GUI 在依赖的，不能随便改？

## 当时的想法

直觉上以为"后端就那几个文件，GUI 不读源码应该不知道细节"。
但实际上 GUI 会通过**接口契约**消费后端——契约破坏了 GUI 就崩。

> **2026-06-29 更新**：接入 agent 单轮闭环（F5/F6）与工具系统后，TUI 与后端的对接面
> 发生了**层级上移**——TUI 不再直接调 `provider.stream`，而是消费 `Agent.run()` 产出的
> `Event` 流。原问答里的"四个对接点"和所有行号均已失效，下面是重写后的当前状态。

## 解答

TUI 真正接触后端的代码只有两处：

- `src/furflycode/tui/app.py` —— 创建 provider、持有 `conv` 与 `_tool_registry`、
  拉起消费任务（`app.py:219` 起 `consume_agent_events(self)`）
- `src/furflycode/tui/stream.py` —— 构造 `Agent(app.provider, app._tool_registry)`，
  消费 `agent.run(app.conv)` 事件流并分派渲染（`stream.py:43-45`）

整个后端对外暴露的就是 **六个对接点**，守住它们 GUI 就完全无感：

### 1. `Agent` + `Event` / `ToolEvent` / `Phase`（`agent/__init__.py`）⭐ 主契约

这是 TUI 现在唯一消费的后端流。`Agent.run(conv) -> AsyncIterator[Event]`，TUI 按 `Event`
非空字段分派渲染（`stream.py:_dispatch`）：

| Event 字段 | TUI 行为 |
|---|---|
| `err` | 出错收尾，渲染错误块，回 IDLE |
| `text` | 追加到 `cur_reply`，刷新流式区 |
| `tool`（`Phase.START`） | 提交 preamble 到 scrollback，切到工具执行指示 |
| `tool`（`Phase.END`） | 写工具行 + 结果摘要，清空工具指示 |
| `done` | 成功收尾，回 IDLE |

**关键**：`Event` 是 TUI 看到的全部。要新增渲染维度（如 usage 统计、思考展示），先在
`Event` 上加字段，再同步 `stream.py:_dispatch`——这是**唯一需要碰 GUI 的地方**。
`Phase` 枚举值、`ToolEvent` 字段同理别删/别改语义。

### 2. `Provider` Protocol（`llm/__init__.py:92`）

TUI **不再直接调用** `provider.stream`（由 `Agent` 内部调用），但仍通过两个 `@property`
读状态栏信息：

| TUI 怎么用 | 后端必须提供 |
|---|---|
| `provider.name` / `provider.model` | 两个只读 `@property` → `str`（状态栏依赖） |

`stream()` 的**签名已变**为 `stream(msgs, tools)`，产出契约由 `Agent` 消费：

- 文本增量 → `StreamEvent(text=...)`
- 工具调用请求 → `StreamEvent(tool_calls=[ToolCall, ...])`（在 `done` 之前发出）
- 正常结束 → `StreamEvent(done=True)`
- 出错 → `StreamEvent(err=Exception)`
- thinking 增量**丢弃**，不产出

### 3. `StreamEvent` / `ToolCall` / `ToolResult` / `ToolDefinition`（`llm/__init__.py`）

`StreamEvent` 现在是**四字段**（不再是三字段）：`text / tool_calls / done / err`。
这是 `Agent` 与 `Provider` 之间的契约，TUI 不直接见，但 `Agent` 内部按此分派
（`agent/__init__.py:90-100`）。改 `StreamEvent` 字段语义会牵动 `Agent.run` 的消费逻辑，
进而影响 TUI 看到的 `Event` 流——属于"后端内部联动"，不直接动 GUI。

配套的协议无关类型：

- `ToolCall(id, name, input)` —— 模型发起的一次工具调用（`input` 为 raw JSON 串）。
- `ToolResult(tool_call_id, content, is_error)` —— 一次执行结果。
- `ToolDefinition(name, description, input_schema)` —— 注册中心导出给 provider 的定义。

### 4. `Message` / `Conversation`

- `Message`（`llm/__init__.py:62`）：`role: "user"|"assistant"|"tool"` + `content: str`，
  外加 `tool_calls`（仅 assistant）/ `tool_results`（仅 tool 轮）。**不再是两字段。**
- `Conversation`（`conversation.py`）：`add_user / add_assistant /
  add_assistant_with_tool_calls / add_tool_results / messages()`。

注意：TUI 现在只调 `conv.add_user`（`app.py:210`）和构造时持有 `conv`——**会话历史由
`Agent` 维护**（`agent/__init__.py` 内部调 `add_assistant` / `add_assistant_with_tool_calls`
/ `add_tool_results`）。TUI 不再回灌回复（原 `stream.py:69` 的 `add_assistant` 已移除）。
所以这些方法的契约只对 `Agent` 关键，对 TUI 只需保证 `add_user` + `messages()` 稳定。

### 5. `tool.Registry` / `Tool` / `Result`（`tool/__init__.py`）

新增的对接面。TUI 持有一个 `Registry`（`app.py:136`，默认 `Registry()`，可注入）并交给
`Agent`。`Agent` 通过它：

- `registry.definitions()` —— 导出 `ToolDefinition` 列表喂给 provider（`agent/__init__.py:85`）。
- `registry.execute(name, args, timeout)` —— 按名执行，**永远返回 `Result`，不抛异常**
  （`tool/__init__.py:101`，未知/超时/异常都包成 `Result(is_error=True)`）。

`Tool` Protocol（`name/description/parameters/execute`）是后端工具实现的契约；`Registry`
的 `register/get/definitions/execute` 签名是 GUI 间接依赖的稳定面。加新工具走
`new_default_registry` 注册即可，GUI 无感。

### 6. `Config.load` / `ProviderConfig` / `new_provider`

TUI 只消费 `config.providers`，**不读** `api_key` / `base_url` / `thinking` 这些后端专属字段。
加新协议、新参数改 `ProviderConfig` + `new_provider`（`llm/__init__.py:126`）即可，状态栏只
依赖 `name` 和 `model`。**这两个字段别删**。加新协议（Gemini、Ollama）在 `new_provider`
里加 `elif`，实现满足 `Provider` Protocol 的类即可——GUI 永远只通过这个工厂拿 provider。

## 决策

后端工作的优先级（已随 agent 层落地而调整）：

1. **守住 `Agent.run()` 的 `Event` 产出契约**——这是 TUI 的主依赖。改工具执行流程、
   改单轮闭环逻辑、改 thinking 处理，都在 `Agent` 内部，对 GUI 透明。
2. **要扩展渲染维度时，先扩 `Event` / `ToolEvent`，再同步 `stream.py:_dispatch`**——
   唯一会和 GUI 联动的改动点。改 `StreamEvent` 只牵动 `Agent`，不直接动 GUI。
3. **加协议/参数走 `ProviderConfig` + `new_provider`**——GUI 无感。
4. **加工具走 `new_default_registry` + `Tool` Protocol**——`Registry` 对外签名稳定即可，
   GUI 无感。
5. **永远别让 GUI 直接依赖具体 provider 类或 `Provider.stream`**——它只认 `Provider`
   Protocol 的 `name`/`model`，以及 `Agent.run` 的 `Event` 流。

## 参考

- `src/furflycode/agent/__init__.py` —— agent 编排层 + `Event`/`ToolEvent`/`Phase`
- `src/furflycode/llm/__init__.py` —— 协议层：`Provider` Protocol(`:92`)、`StreamEvent`(`:75`)、
  `Message`(`:62`)、`new_provider`(`:126`)
- `src/furflycode/conversation.py` —— 会话层（含工具调用/结果轮次）
- `src/furflycode/tool/__init__.py` —— 工具抽象 + `Registry`(`:71`)
- `src/furflycode/config.py` —— 配置层
- `src/furflycode/tui/stream.py:38-79` —— TUI 消费 `agent.run` 事件流的唯一位置
- `src/furflycode/tui/app.py:129-220` —— TUI 持有的后端引用（providers / provider / conv /
  _tool_registry）与消费任务拉起
