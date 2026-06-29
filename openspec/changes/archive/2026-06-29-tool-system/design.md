## Context

本次变更在 chat-client「provider → conversation → tui」三件套之上新增工具系统。chat-client 已是多协议、流式、多轮上下文的终端对话客户端，但模型「只能动嘴」。本次变更给 FurflyCode 装上工具系统：用户提问 → 模型识别要用哪个工具 → 代码执行 → 结果回灌 → 模型给出最终答复，从「聊天机器人」进化为「能干活的 Agent」。

### 架构与新增/扩展模块

在 chat-client 三件套之上，新增两个包并扩展三处：

- **furflycode.tool（新建）**：统一工具抽象 `Tool`、执行结果 `Result`、注册中心 `Registry`、6 个核心工具。零外部依赖，不感知 LLM 协议。
- **furflycode.agent（新建）**：承载「单轮闭环」编排——请求#1（带工具）→ 收集工具调用 → 注册中心执行 → 结果回灌进 `Conversation` → 请求#2（续答）→ 最终文本 → 停。对外吐出一条 `Event` async generator 供 TUI 渲染。只依赖 `llm`、`tool`、`conversation`，不 import anthropic/openai，保持协议无关。
- **furflycode.llm（扩展）**：`Message`/`StreamEvent` 增加工具字段；新增协议无关类型 `ToolCall`/`ToolResult`/`ToolDefinition` 与 `ROLE_TOOL` 常量；`Provider.stream` 增加 `tools` 参数；两个适配器注入工具定义、解析流式工具调用、回灌工具结果。
- **furflycode.conversation（扩展）**：新增「assistant 工具调用回合」与「工具结果回合」的追加方法。
- **furflycode.prompt（扩展）**：`SYSTEM_PROMPT` 增补 Agent 角色与工具使用约定。
- **furflycode.tui（扩展）**：`submit` 改走 `Agent.run`；事件消费 task 处理工具事件；渲染 Claude Code 风格工具行与执行指示。
- **cli.py（扩展）**：构造 `tool.new_default_registry()` 并注入 `FurflyCodeApp`。

### 依赖方向（无环）

`tool → llm`；`conversation → llm`；`agent → {llm, tool, conversation}`；`tui → {agent, tool, conversation, llm, prompt}`；`llm → {config, prompt}`。

### 核心数据结构

**llm 包**：新增 `ROLE_TOOL = "tool"`；`ToolCall(id, name, input)`（input 为拼接完成的 raw JSON 字符串）；`ToolResult(tool_call_id, content, is_error)`；`ToolDefinition(name, description, input_schema)`。`Message` 扩展 `tool_calls`（仅 assistant）与 `tool_results`（仅 ROLE_TOOL）字段，`role` 字面量扩展为 `Literal["user", "assistant", "tool"]`。`StreamEvent` 扩展 `tool_calls` 字段（turn 结束时一次性上抛）。`Provider.stream` 签名改为 `stream(self, msgs: list[Message], tools: list[ToolDefinition]) -> AsyncIterator[StreamEvent]`，`tools` 为空表示本次请求不带工具。

**tool 包**：`Result(content, is_error)`（永远以值类型返回，从不抛 Python 异常给上层）；`Tool` Protocol（`name()`/`description()`/`parameters()`/`async execute(args) -> Result`，args 为 raw JSON 字符串，超时由外部 `asyncio.wait_for` 控制）；`Registry`（`register`/`get`/`definitions`/`async execute(name, args, timeout)`）；`new_default_registry()`；`DEFAULT_TIMEOUT = 30.0`。

**agent 包**：`Phase`(START/END)、`ToolEvent`(name/args/phase/result/is_error)、`Event`(text/tool/done/err)、`Agent(provider, registry)` 持有 provider 与注册中心执行单轮闭环，`run(conv) -> AsyncIterator[Event]`。

各工具的参数 Schema、成功/错误结果约定：

| 工具名 | 参数（JSON Schema） | 成功结果 | 错误结果 |
|--------|--------------------|---------|---------|
| `read_file` | `path`(必填) | 带行号文本（`f"{n:6d}\t{line}"` 风格，≤2000 行 / ≤256KB，超出截断标注 `[truncated]`） | 不存在/不可读/是目录 |
| `write_file` | `path`(必填)、`content`(必填) | `Path.parent.mkdir(parents=True, exist_ok=True)` 后覆盖写，返回路径与字节数 | 写入失败 |
| `edit_file` | `path`、`old_string`、`new_string`(均必填) | `content.count(old)==1` 时唯一替换并写回 | 0 处→「未找到匹配」；>1 处→「匹配到 N 处，old_string 不唯一，请提供更长上下文」 |
| `bash` | `command`(必填) | `asyncio.create_subprocess_shell(..., stdout=PIPE, stderr=PIPE)` 执行，返回 stdout/stderr/exit_code（合并视图截断 ~30000 字符） | 超时（is_error）；命令非零退出按结果回灌 |
| `glob` | `pattern`(必填，如 `**/*.py`)、`path`(可选，默认 cwd) | `pathlib.Path(root).rglob(pattern)` 匹配（≤100，排序） | 无匹配返回空说明（非 is_error） |
| `grep` | `pattern`(必填，Python 正则)、`path`(可选)、`glob`(可选文件名过滤) | `re.compile` + 逐行扫，`file:line:content` 列表（≤100，超出标注） | 正则非法（is_error）；无命中返回空说明 |

### 模块设计概要

- **furflycode.tool**：提供 6 个工具的统一抽象与执行；集中登记与导出；所有失败包成 `Result(is_error=True)` 而非抛异常。对外接口 `Tool`/`Result`/`Registry`/`new_default_registry`/`DEFAULT_TIMEOUT`。依赖标准库（`pathlib`/`asyncio`/`re`/`fnmatch`/`json`）与 `furflycode.llm`（仅为 `definitions()` 返回 `list[ToolDefinition]`）。关键点：Schema 手写为 `dict[str, Any]`；`read_file` 带行号与行/字节上限；`edit_file` 唯一匹配语义 + 含计数可区分错误；`bash` 用 `asyncio.create_subprocess_shell` + 外层 `asyncio.wait_for` 控超时，超时 `proc.kill()`；`glob`/`grep` 遍历期间 `await asyncio.sleep(0)` 让出 event loop；空 args（OpenAI 可能给空串而非 `{}`）归一为 `"{}"`。
- **furflycode.agent**：单轮闭环编排，保证单轮上限；把 provider 的 `StreamEvent` 与工具执行翻译成统一 `Event` 异步流。对外接口 `Agent`/`Event`/`ToolEvent`/`Phase`。run 算法：取 `defs` → 请求#1 转发 text 增量、累积 preamble、收集 tool_calls → 无 calls 则 `add_assistant(preamble)` 后 `done` → 有 calls 则 `add_assistant_with_tool_calls` 后顺序执行每个 call（START/END 事件 + 收集 `ToolResult`）→ `add_tool_results` → 请求#2 转发最终答复 text、**忽略**其返回的 tool_calls（单轮）→ `add_assistant(final)` 后 `done`。调用方 `cancel()` 该 task 时 `CancelledError` 沿向上传播终止。
- **furflycode.llm（扩展）**：协议无关请求/响应抽象 + 两协议工具调用全流程。`anthropic_provider.py`：请求加 `to_anthropic_tools`；流循环用 `async with self._client.messages.stream(**params) as stream:`，按 `event.type` 分派（`text_delta` → 文本增量，`thinking_delta`/`input_json_delta` 跳过）；流结束取 `stream.get_final_message()`，若 `stop_reason == "tool_use"` 遍历 `ToolUseBlock` 收集 `ToolCall`；`to_anthropic_messages` 扩展支持 assistant tool_use 回合与 `ROLE_TOOL` tool_result 回合（拼进一条 user 消息的 content 数组）；含工具历史的请求关闭 thinking 以避免 400。`openai_provider.py`：请求加 `to_openai_tools`；流循环按 index 维护 `tool_calls_buf` 累加合并 `delta.tool_calls` 片；流结束按 index 排序组 `ToolCall`（空 arguments 归一 `"{}"`）；`to_openai_messages` 扩展支持 assistant.tool_calls 与每个 `ToolResult` 一条 tool 角色消息。
- **furflycode.conversation（扩展）**：新增 `add_assistant_with_tool_calls(text, calls)` 与 `add_tool_results(results)`，保留现有方法不变。
- **furflycode.tui（扩展）**：渲染 `agent.Event`（文本/工具行/结果摘要/错误/结束），保持非阻塞。`FurflyCodeApp.__init__` 接 `registry`；新增 `_cur_tool` 执行中指示成员；`submit` 走 `asyncio.create_task(self._consume_agent_events())`，内部构造 `Agent` 后 `async for ev in agent.run(self.conv):` 分派；`view.py` 新增 `tool_line`/`tool_result_summary` 与执行指示渲染。单 event loop 内 `RichLog.write` 同步追加保证顺序。

### 模块交互

用户提交 → `FurflyCodeApp.submit`（`conv.add_user` + `create_task(_consume_agent_events)`）→ `_consume_agent_events` 构造 `Agent` 并 `async for ev in agent.run(conv):` → 请求#1（`provider.stream(conv.messages(), registry.definitions())`，适配器注入 tools → 流式拼接 → `StreamEvent{text}`/`StreamEvent{tool_calls}`）→ agent 转发 `Event{text}` 并收集 calls → 无 calls 则 `add_assistant` 后 `done`；有 calls 则 `add_assistant_with_tool_calls` → 顺序执行每个 call（`Event{tool=START}` → `registry.execute` → `Event{tool=END}`）→ `add_tool_results` → 请求#2 → 转发最终答复 `Event{text}` → `add_assistant(final)` 后 `Event{done}` → `_consume_agent_events` 按 Event 类型渲染（cur_reply 动态区 / RichLog.write 进 scrollback）。

并发：`conv` 仅在单个 event loop 上被消费 task 触碰——`submit` 在 `create_task` 前 `add_user`，之后只读；`run` 协程独占后续所有 `conv` 变更；`messages()` 返回副本。Textual UI 渲染回到主协程序列化执行，与 `conv` 互不干扰。

## Goals / Non-Goals

**Goals:**
- 提供统一的工具抽象：每个工具暴露名称、描述、参数 Schema、执行入口。
- 落地六个核心工具：读文件、写文件、改文件、执行命令、按模式找文件、搜代码内容。
- 提供注册中心：集中登记工具、按名查找、导出为 API 认得的工具定义列表。
- 工具执行带超时与结构化错误——失败包成结果回传给模型，不崩溃、不中断会话。
- LLM 客户端能解析流式工具调用（拼接分片的 JSON 参数），把工具调用与执行结果回灌进对话历史。
- 单轮闭环 + 续答：模型请求工具 → 执行 → 结果回灌 → 模型再生成一次最终文本答复 → 停。本次变更不做连环调用。
- Anthropic 与 OpenAI 两种协议都支持工具调用全流程，保持跨协议一致体验。
- 工具调用在 TUI 以 Claude Code 风格工具行呈现（如 `● Read(path)` + 结果摘要）。

**Non-Goals:**
- 多工具连环调用 / Agent Loop：模型拿到一次工具结果并给出最终答复后即停；不自动多轮反复调用工具，多轮循环不在本次范围内。
- 权限系统：工具执行（含写文件、执行命令）本次变更不做授权确认，仅靠超时与结构化错误约束，授权确认属于未来工作。
- 工具执行沙箱 / 路径白名单：不限制工具只能在工作目录内操作；不做路径越界防护，沙箱与白名单属于未来工作。
- 工具调用中断 / 取消：本次变更不支持中途取消正在执行的工具或正在进行的回复（沿用 chat-client）。
- 工具调用与结果持久化：工具调用与结果不落盘，退出即丢（沿用 chat-client）。
- 工具行的折叠 / 展开交互：UI 仅展示工具行 + 结果摘要，不做可交互折叠或详情展开。
- 配置化工具集 / 自定义工具：工具集固定为这六个，不支持运行时增删或通过配置开关启停。
- 超时时长配置化：超时为内置合理默认值，本次变更不通过配置调整。
- 多模态工具结果：工具结果均为文本，不含图片等非文本产物。
- 并行工具的并发执行优化：一次回复中的多个工具调用按顺序执行即可，本次变更不追求并发加速。

## Decisions

- **工具调用循环放哪** → 选择：新建 `furflycode.agent` 包，TUI 退化为渲染器。理由：循环（请求#1→执行→请求#2）无法塞进单个 `_consume_stream` 协程；独立包可无 UI 单测，只依赖 llm+tool+conversation，不泄漏 SDK 类型。命名 `agent` 而非 `runner`：概念即 Agent，本次变更恰为单轮。备选：塞进 TUI 协程（不可单测、耦合 UI）。
- **是否用 SDK 的高级 tool-runner** → 选择：不用，坚持手写 streaming + 手动单轮。理由：anthropic Python SDK 暂无自动 tool runner；openai 的 helper 自动连环到完成，违反单轮约束。手写迭代更可控且与既有实现风格一致。备选：用 openai helper（违反单轮闭环约束）。
- **工具定义传入哪一层** → 选择：`Provider.stream` 第二参数 `list[ToolDefinition]`。理由：两 SDK 都把 tools 放 per-request params；续答仍需带；保持 Provider 无状态。备选：在 Provider 构造时注入（破坏无状态与可复用）。
- **工具参数 Schema 生成** → 选择：每工具手写 `dict[str, Any]`。理由：OpenAI `parameters` 与 Anthropic `input_schema` 都直接吃 JSON Schema dict；6 个固定工具手写最直白，描述对模型可读性最关键；不引入 `pydantic` 反射（schema 还要剥 `$defs`/`additionalProperties` 噪音）。备选：pydantic 反射（schema 噪音多）。
- **流式工具参数拼接** → 选择：Anthropic 用 `stream.get_final_message()` 拿汇总；OpenAI 按 `delta.tool_calls[i].function.arguments` 按 index 累加。理由：Anthropic SDK 自带累加器，避免手写 PartialJSON 边界；OpenAI 必须按 index 拼接（多工具下同时分片）。备选：Anthropic 手写 PartialJSON 累加器（易错）。
- **Glob/Grep 实现** → 选择：纯标准库（`pathlib.glob`/`re` + 异步 `await asyncio.sleep(0)` 让出）。理由：零额外依赖、跨平台；spec 要求保持简单、不引入配置。备选：引入 ripgrep 包装（额外依赖、跨平台麻烦）。
- **Bash 实现与超时** → 选择：`asyncio.create_subprocess_shell` + `asyncio.wait_for(..., DEFAULT_TIMEOUT)`。理由：`shell=True` 自带管道/重定向；asyncio 原生超时 + `proc.kill()` 终止；30s 内置不可配（spec：超时不配置化）。跨平台兼容（Win 上 asyncio 走 ProactorEventLoop）。备选：自实现进程超时守护线程（复杂）。
- **工具失败的表达** → 选择：`execute` 返回 `Result(content, is_error)`，从不抛异常给上层。理由：所有失败包成结构化结果回灌，程序不崩，上层无需区分 try/except 路径。备选：抛异常由上层 catch（上层负担重、易漏接导致崩溃）。
- **工具结果在 Message 的形态** → 选择：平铺字段（assistant 加 `tool_calls`，`ROLE_TOOL` 加 `tool_results`）。理由：两 SDK 工具语义本就是 id 关联的 tool_use/tool_result 列表；通用 content-block 联合属过度设计（本次变更结果均文本）。适配器吸收差异（Anthropic 结果进 user 消息、OpenAI 用 tool 角色）。备选：通用 content-block 联合（过度设计）。
- **UI 截断 vs 回灌截断** → 选择：两者分离：UI 摘要 ~8 行；回灌为工具级上限（read 2000 行 / bash 30000 字符等）。理由：界面需截断简洁，但模型需较完整内容；尾部统一加 `[truncated]` 标注。备选：UI 与回灌共用同一截断（模型信息不足或界面撑爆）。
- **续答请求是否带 tools** → 选择：带，但忽略其返回的工具调用。理由：与真实协议一致（OpenAI assistant+tool 后不带 tools 也可，但带更稳）；单轮由 agent 不再触发执行来保证。备选：续答不带 tools（部分兼容端点可能报错）。
- **thinking 与工具组合** → 选择：历史含工具交互的请求（续答）不启用 thinking。理由：Anthropic 在 thinking 启用时要求回灌带 tool_use 的 assistant 回合附原 thinking 块（含 signature），而本次变更按 spec 丢弃 thinking 增量、不留签名；故对这类请求关闭 thinking 以避免 400。备选：续答保留 thinking 块与签名（违反 spec 丢弃 thinking 增量）。
- **空最终答复** → 选择：续答为空时用单轮提示占位并推给 UI。理由：空 assistant 回合会破坏下一轮请求（Anthropic 要求非空内容 + 角色交替）；占位提示同时满足「单轮上限提示」。备选：留空 assistant 回合（破坏下一轮请求）。
- **空参数归一** → 选择：OpenAI 侧空 arguments 归一为 `"{}"`。理由：无参工具的 arguments 可能为空串，回灌时须是合法 JSON，否则严格兼容端点对 `"arguments": ""` 返回 400。备选：原样透传空串（严格端点 400）。
- **grep 超长行** → 选择：显式标注未完整搜索。理由：`for line in file` 遇超长行可能阻塞或读爆内存；用 `read(chunk)` + 手动分割或 `iter(..., '')` 加最大长度判定，超出标注「该行过长，未完整搜索」避免假「无命中」误导模型。备选：逐行读不设上限（内存风险）。
- **scrollback 顺序提交** → 选择：单 event loop 内 `RichLog.write` 同步追加。理由：Python 的 asyncio 单线程模型天然保证顺序；不存在 Go `tea.Batch` 并发乱序问题。备选：引入额外同步原语（无必要、增复杂度）。
- **工具命名** → 选择：`read_file`/`write_file`/`edit_file`/`bash`/`glob`/`grep`。理由：符合 OpenAI 函数名规则（`a-zA-Z0-9_-`）与 Claude Code 习惯；TUI 工具行显示 `● name(关键参数)`。备选：其他命名风格（不符合函数名规则或不符合习惯）。

## Risks / Trade-offs

- [风险] 单轮上限可能让部分任务无法在一轮内完成（模型在续答中仍想调用工具被忽略） → 缓解：单轮闭环已明确为本次变更的 Non-Goal，连环调用 / Agent Loop 不在本次范围；续答为空时以单轮上限提示占位，给用户可观察的停止信号。
- [风险] 工具执行无权限/沙箱约束，`bash`/`write_file` 可对工作目录外操作 → 缓解：本次变更靠超时与结构化错误兜底，权限系统与路径白名单明确作为未来工作不在本次范围；不限制是刻意的 scope 决策。
- [风险] Anthropic thinking 与工具历史组合在协议层有签名约束 → 缓解：对含工具历史的请求关闭 thinking，避免 400；代价是这类请求无思考增量（spec 本就丢弃思考增量，无损失）。
- [风险] OpenAI 兼容端点对空 arguments、tool 角色消息格式严格 → 缓解：空 arguments 归一为 `"{}"`；按 index 拼 tool_calls；每个 ToolResult 发一条 tool 角色消息，严格遵循 OpenAI 线格式。
- [风险] 超长 grep 行 / 大文件可能阻塞或读爆内存 → 缓解：grep 超长行显式标注「未完整搜索」；read/bash/grep 各设工具级上限并尾部标注 `[truncated]`。
- [风险] 多工具一次回复下流式分片乱序 → 缓解：OpenAI 按 index 累加合并；Anthropic 用 SDK 累加器；UI 在单 event loop 内同步追加保序。
- [取舍] UI 截断（~8 行）与回灌截断（工具级上限）分离：界面简洁但模型拿到的内容与界面展示不一致，需分别维护两套截断逻辑。
- [取舍] 超时为内置默认值不可配：实现简单、符合 spec，但用户无法为长任务放宽超时，配置化作为后续工作不在本次范围。
- [取舍] 工具集固定为六个、不可配置：降低复杂度，但无法运行时增删或自定义工具，自定义工具作为未来工作不在本次范围。
