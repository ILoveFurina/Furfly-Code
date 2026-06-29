## Context

furflycode 是从零构建的 Claude Code 风格终端 AI Agent，本 change 是其第一块基石，打通"人 ↔ LLM"的最小闭环。技术栈：Python 3.12+；TUI 用 Textual（async-first，原生跑在 asyncio 上）+ Rich（`rich.markdown.Markdown` 渲染）+ Textual CSS；配置用 `pyyaml`；LLM 通信用官方 Python SDK（`anthropic` 的 `AsyncAnthropic`、`openai` 的 `AsyncOpenAI`，均原生支持 async 流式，SDK 内部已处理 SSE）。

分层架构（源码在 `src/furflycode/`）：
1. 入口层 `furflycode.cli`：加载配置、打印 banner、启动 Textual App。
2. 配置层 `furflycode.config`：读取并校验 `.furflycode/config.yaml`，给出 providers 列表。
3. LLM 协议层 `furflycode.llm`：定义协议无关的 `Provider` Protocol 与统一消息/流式事件类型；anthropic、openai 两个适配器各自封装官方 SDK、统一吐出文本增量（思考增量内部丢弃）。
4. 会话层 `furflycode.conversation`：进程内维护多轮历史，提供完整上下文。
5. 提示词/资源 `furflycode.prompt`：内置 system prompt 与启动 banner（ASCII 猫）。
6. 终端层 `furflycode.tui`：Textual App，含状态机（选择/空闲/流式）、输入框、对话区、loading 计时、provider 选择列表；以 async task 消费 `Provider.stream(...)` 的事件生成器。

数据流（一轮对话）：用户输入 → TUI 提交 → conversation 追加 user 消息 → 调 `Provider.stream(msgs)` → 得到 `AsyncIterator[StreamEvent]` → TUI async task 逐个 `async for` 读文本增量并实时追加（loading 计时同步进行）→ 收到结束事件 → 用 Rich Markdown 渲染整段 → conversation 追加 assistant 消息 → 回到空闲。

核心数据结构：
- `ProviderConfig`（name、protocol、api_key、model、base_url、thinking）与 `Config(providers)`。
- `Message(role, content)` 与 `StreamEvent(text, done, err)`（done 与 err 互斥）。
- `Provider` Protocol：`name`/`model` property 与 `stream(msgs) -> AsyncIterator[StreamEvent]`。
- `Conversation`：`add_user`/`add_assistant`/`messages()`（返回副本）。
- `SessionState` 枚举：`SELECTING` / `IDLE` / `STREAMING`。

备注：Python 的 Textual + asyncio 是 async-first 体系，直接 `async for event in provider.stream(...)` 即可驱动 UI，没有 goroutine / channel / `tea.Cmd` 的胶水层。

## Goals / Non-Goals

**Goals:**
- 打通 LLM API 调用：能向大模型发起请求并正确接收回复。
- 同时支持 Anthropic 与 OpenAI 两种协议，通过一份配置切换接入对象（含兼容端点）。
- 提供一个全功能终端界面（TUI），承载输入、流式输出与多轮对话。
- 回复以流式方式实时呈现，结束后以 markdown 形式美化展示。
- 在单次会话内维护完整对话上下文，支持连续多轮交流。
- 对调用失败有可恢复的错误反馈，不中断会话。

**Non-Goals:**
- 工具调用 / function calling：不发送工具定义、不处理工具调用，纯文本对话。
- MCP 集成：不连接任何 MCP server。
- 权限系统：无任何需授权的操作。
- 上下文压缩：历史增长不做摘要/截断，超长由用户自行控制。
- 长期记忆 / 跨会话记忆：不做。
- 会话持久化：历史不落盘、不支持重启恢复或续聊。
- slash 命令体系：除 `/exit` 外，不做可扩展命令系统（如 `/help`、`/clear`、`/model` 等）。
- 运行时切换 provider / model：多份配置仅在启动时选一次。
- thinking 内容展示：扩展思考增量接收即丢弃，不渲染、不折叠展示。
- 流式中断：不支持取消正在进行的回复。
- 自动重试 / 限流退避：出错仅提示，不自动重试。
- 其它配置来源：仅读 YAML 配置文件，不做环境变量 / 命令行 flag 覆盖。
- 用量统计：不显示 token 数与费用（但保留响应耗时计时）。
- 多模态：不支持图片等非文本输入。

## Decisions

### 语言
- 选择：Python 3.12+
- 理由：3.12 的 typing / `asyncio.TaskGroup` 等更舒服。
- 备选：无显著备选。

### TUI 框架
- 选择：Textual
- 理由：async-first，原生跑在 asyncio 上；CSS 样式、widget 丰富；与流式 SDK 天然契合。
- 备选：无（用户已选定方向）。

### markdown 渲染
- 选择：Rich 的 `rich.markdown.Markdown`
- 理由：Textual 内部即用 Rich；代码块语法高亮、列表、强调齐全；宽度自适应终端列宽。
- 备选：无。

### LLM 通信
- 选择：官方 Python SDK（`anthropic` / `openai`）
- 理由：用户选定；SDK 内置 SSE 解析与 async 流，省去手写；`AsyncAnthropic` / `AsyncOpenAI` 即可。
- 备选：手写 HTTP/SSE 客户端（被否决，因 SDK 已封装且更稳）。

### 协议抽象
- 选择：统一 `Provider` Protocol + 两适配器
- 理由：上层不感知协议，新增协议只需实现接口并注册。
- 备选：直接在 TUI 内分支两种协议（被否决，会破坏一致性与可扩展性）。

### 流式接入 TUI
- 选择：`async for event in provider.stream(...)` 直跑在 Textual 的事件循环里
- 理由：Python async-first，无需 channel/Cmd 胶水；界面不阻塞。
- 备选：独立线程 + 队列（被否决，async-first 体系不需要）。

### 流式渲染策略
- 选择：流式纯文本 + done 后 `rich.markdown.Markdown` 定型
- 理由：markdown 需完整块；增量渲染会抖动，定型时机后置以避免。
- 备选：增量 markdown 渲染（被否决，会抖动）。

### 渲染模型
- 选择：inline + `RichLog.write(...)` 追加（Claude Code 风格）
- 理由：完成消息持久写入 RichLog，可滚动回看；仅"输入框 + 正在流式的回复 + 状态栏"为动态重绘区。
- 备选：自管消息列表每帧全量重绘（被否决，开销大且难滚动）。

### thinking 处理
- 选择：仅 anthropic 生效（`thinking={"type":"enabled",...}`）；openai 忽略
- 理由：OpenAI reasoning 不经 chat.completions 返回正文；思考内容本就丢弃。
- 备选：无。

### 计时
- 选择：`turn_start = time.monotonic()` + `set_interval(0.1, ...)` 计算 elapsed
- 理由：自请求即计时，由 Textual 内置 timer 驱动刷新。
- 备选：无。

### provider 选择
- 选择：单份直进 / 多份 `OptionList` 选择
- 理由：单份配置直进最省事，多份配置用方向键列表选定。
- 备选：无。

### 历史管理
- 选择：进程内 `list[Message]`，单会话
- 理由：进程内维护单会话历史即可，不持久化。
- 备选：持久化存储（被否决，明确 Non-Goal）。

### system prompt 注入
- 选择：内置常量，适配器注入
- 理由：system 提示词由适配器注入，conversation 保持纯 user/assistant 消息。
- 备选：conversation 层携带 system 消息（被否决，会污染对话模型）。

### 配置
- 选择：`.furflycode/config.yaml` + `pyyaml`；密钥入 `.gitignore`
- 理由：用户既定路径；密钥入 `.gitignore` 保证不泄露。
- 备选：环境变量 / 命令行 flag 覆盖（被否决，明确 Non-Goal）。

### 错误处理
- 选择：运行时错误经 `StreamEvent.err` 显示，不退出
- 理由：运行时错误经 `StreamEvent.err` 透出，会话不中断。
- 备选：异常上抛导致退出（被否决，违背会话不中断原则）。

### 类型与质量
- 选择：`typing.Protocol` + `dataclass`；`ruff format` + `ruff check` + 可选 `mypy`
- 理由：简洁，无运行时依赖（vs pydantic）；ruff 一站式格式化/lint。
- 备选：pydantic 做配置校验（被否决，引入运行时依赖不必要）。

## Risks / Trade-offs

- [流式渲染抖动] → 流式期间只用纯文本逐字显示，done 后再用 `rich.markdown.Markdown` 整段定型，避免增量 markdown 渲染抖动。
- [markdown 增量渲染不可靠] → 同上策略，渲染时机后置到本轮结束。
- [界面阻塞风险] → 直接在 Textual 的 asyncio 事件循环里 `async for` 消费流，天然不阻塞；完成消息走 `RichLog.write` 追加而非全量重绘。
- [密钥泄露] → `.furflycode/config.yaml` 入 `.gitignore`；密钥不回显、不打印到对话区或日志。
- [配置错误导致崩溃堆栈] → `config.load` 统一捕获文件缺失/YAML 解析错误/字段校验失败，转 `ConfigError` 可读信息，入口 `sys.exit(1)`。
- [退出残留终端状态] → 退出时 `task.cancel()` 终止进行中的流，依赖 Textual 自动还原 raw mode。
- [跨协议行为不一致] → 统一 `Provider` Protocol 与 `StreamEvent` 抽象，两适配器都吐出相同形态事件，上层不感知协议。
- [窄屏错版] → CSS 设置 `#streaming` / `Markdown` / `RichLog` 为 `width: 1fr;` 自适应，依赖 Textual + Rich 默认软换行避免窄屏错版。
- [thinking 混入正文] → anthropic 适配器识别 `thinking_delta` 即丢弃，openai 适配器忽略 thinking 字段。
- [流式取消] → 本期不支持流式中断（明确 Non-Goal），退出时通过 `task.cancel()` + `async with` 上下文清理 SDK 流。
