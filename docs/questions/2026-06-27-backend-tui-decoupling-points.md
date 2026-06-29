---
status: answered
tags: [architecture, backend, tui, decoupling]
created: 2026-06-27
answered: 2026-06-27
related:
  - 2026-06-27-provider-protocol-and-runtime-checkable.md
  - 2026-06-27-protocol-vs-abc-design-choice.md
---

# 不关注 GUI 逻辑，但想正确处理后端逻辑，应该关注什么对接点？

## 背景

想专注做后端（LLM 协议层、会话层、配置层），不想被 TUI 的渲染、状态机、事件循环分心。
但又必须知道：哪些契约是 GUI 在依赖的，不能随便改？

## 当时的想法

直觉上以为"后端就那几个文件，GUI 不读源码应该不知道细节"。
但实际上 GUI 会通过**接口契约**消费后端——契约破坏了 GUI 就崩。

## 解答

TUI 真正接触后端的代码只有两处：

- `src/furflycode/tui/app.py` —— 创建/读取 provider
- `src/furflycode/tui/stream.py:27` —— 消费流 `app.provider.stream(app.conv.messages())`

整个后端对外暴露的就是 **四个对接点**，守住它们 GUI 就完全无感：

### 1. `Provider` Protocol（`llm/__init__.py:28`）

TUI 只用到三个东西：

| TUI 怎么用 | 后端必须提供 |
|---|---|
| `provider.name` / `provider.model` | 两个只读 `@property` → `str` |
| `provider.stream(msgs)` | async generator，产出 `StreamEvent` |

`stream()` 的产出契约：
- 文本增量 → `StreamEvent(text=...)`
- 正常结束 → `StreamEvent(done=True)`
- 出错 → `StreamEvent(err=Exception)`
- thinking 增量**丢弃**，不产出

### 2. `StreamEvent`（`llm/__init__.py:19`）

三个字段 `text / done / err`。TUI 在 `stream.py:28-36` 按优先级处理：
`err` 优先于 `text`，`done` 收尾。

要扩展能力（如 tool_call、usage 统计）时，先在 `StreamEvent` 上加字段，再同步 `stream.py` 的
消费分支——这是**唯一需要碰 GUI 的地方**。

### 3. `Message` / `Conversation`

- `Message`（`llm/__init__.py:11`）：`role: "user"|"assistant"` + `content: str`
- `Conversation`（`conversation.py`）：`add_user / add_assistant / messages()`

TUI 喂历史（`stream.py:27`）、回灌回复（`stream.py:69`）只用这三个方法。

### 4. `Config.load` / `ProviderConfig`

TUI 只消费 `config.providers`，**不读** `api_key` / `base_url` / `thinking` 这些后端专属字段。
加新协议、新参数改 `ProviderConfig` + `new_provider` 即可，状态栏只依赖 `name` 和 `model`。
**这两个字段别删**。

### 5. `new_provider` 工厂（`llm/__init__.py:56`）

加新协议（Gemini、Ollama）就在这里加 `elif`，实现满足 `Provider` Protocol 的类即可。
GUI 永远只通过这个工厂拿 provider。

## 决策

后端工作的优先级：

1. **守住 `Provider.stream()` 的 `StreamEvent` 产出契约**——改 SDK、改重试、改 thinking
   处理，都在这层内。
2. **要扩展能力时，先扩 `StreamEvent` / `Message`，再同步 `stream.py` 的消费分支**——
   唯一会和 GUI 联动的改动点。
3. **加协议/参数走 `ProviderConfig` + `new_provider`**——GUI 无感。
4. **永远别让 GUI 直接依赖具体 provider 类**——它只认 `Provider` Protocol。

## 参考

- `src/furflycode/llm/__init__.py` —— 协议层 + 工厂
- `src/furflycode/conversation.py` —— 会话层
- `src/furflycode/config.py` —— 配置层
- `src/furflycode/tui/stream.py:21-36` —— GUI 消费流的唯一位置
- `src/furflycode/tui/app.py:128-138` —— GUI 持有的后端引用（provider / conv / cur_reply / turn_start）