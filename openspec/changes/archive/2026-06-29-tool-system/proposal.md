## Why

step1 已打通「人 ↔ LLM」的对话闭环：多协议、流式、多轮上下文的终端对话客户端，但模型「只能动嘴」——无法触碰文件系统或执行命令。用户提问后，模型最多给一段文字建议，不能真正读文件、改代码、跑命令、查代码库。FurflyCode 需要从「聊天机器人」进化为「能干活的 Agent」：模型识别要用哪个工具 → 代码执行 → 结果回灌 → 模型据此给出最终答复。这是让终端 AI 编程助手真正可用的关键一跃。

## What Changes

- 新增统一的**工具抽象**：每个工具暴露名称、给模型看的描述、参数 Schema、执行入口，并以值类型 `Result(content, is_error)` 返回执行结果（从不向上层抛 Python 异常）。
- 新增**注册中心**：集中登记工具、按名查找、按注册顺序导出为协议无关的 `ToolDefinition` 列表。
- 落地**六个核心工具**：`read_file`（带行号读文件）、`write_file`（覆盖写、自动建父目录）、`edit_file`（唯一匹配替换 + 含计数的可区分错误）、`bash`（执行 shell 命令 + 超时）、`glob`（按模式找文件）、`grep`（按正则搜代码内容）。
- 新增**流式工具调用解析**：拼接分片到达的工具名与 JSON 参数碎片，组装出完整工具调用请求；正文文本、思考增量、工具调用三者正确区分（思考增量沿用 step1 接收即丢弃）。
- 新增**工具执行**：按名从注册中心找到工具并执行，受超时保护；无论成功或失败都产出结构化结果，单个工具失败不中断会话。
- 新增**结果回灌与单轮闭环**：将工具调用与执行结果按协议格式追加进对话历史，再次发起请求让模型给出最终文本答复；本轮在最终答复后结束，不做连环调用。
- **跨协议一致**：Anthropic 与 OpenAI 两种协议都支持工具定义注入、流式工具调用解析、结果回灌的全流程，对上层暴露协议无关的统一接口。
- 扩展 **TUI** 以 Claude Code 风格工具行呈现每次工具调用（如 `● read_file(path)` + 缩进结果摘要），随流式实时出现并纳入 scrollback 历史。
- 新增**结构化错误**：工具执行失败（文件不存在、命令超时/非零退出、改文件匹配数不对、搜索无结果等）以结构化结果回灌给模型，UI 以可区分样式提示，程序不崩溃、会话不中断。

## Capabilities

### New Capabilities
- `tool-system`: 统一工具抽象、注册中心、六个核心工具，以及流式工具调用解析、执行、结果回灌的单轮闭环编排与跨协议支持、TUI 工具行呈现、结构化错误处理。

### Modified Capabilities
<!-- 留空。本 change 不修改 step1 chat-client 的 spec 级行为；llm/conversation/tui/cli 的接线属实现细节，不构成对 chat-client 需求的改动。 -->

## Impact

- **新建模块** `src/furflycode/tool/`：`Tool` Protocol、`Result`、`Registry`、`new_default_registry`、`DEFAULT_TIMEOUT`、`_truncate` 辅助，以及 `read_file.py`/`write_file.py`/`edit_file.py`/`bash.py`/`glob_tool.py`/`grep_tool.py` 六个工具实现。零外部依赖，不感知 LLM 协议。
- **新建模块** `src/furflycode/agent/`：`Agent`、`Event`、`ToolEvent`、`Phase`，承载单轮闭环编排（请求#1 带工具 → 收集工具调用 → 注册中心执行 → 结果回灌进 `Conversation` → 请求#2 续答 → 最终文本 → 停），对外吐出 `Event` async generator 供 TUI 渲染。只依赖 `llm`/`tool`/`conversation`，不 import anthropic/openai。
- **扩展** `src/furflycode/llm/`：`__init__.py` 新增 `ToolCall`/`ToolResult`/`ToolDefinition` 与 `ROLE_TOOL` 常量，`Message`/`StreamEvent` 增工具字段，`Provider.stream` 增加 `tools` 参数；`anthropic_provider.py`/`openai_provider.py` 注入工具定义、解析流式工具调用、回灌工具结果。
- **扩展** `src/furflycode/conversation.py`：新增 `add_assistant_with_tool_calls`、`add_tool_results` 两个追加方法。
- **扩展** `src/furflycode/prompt.py`：`SYSTEM_PROMPT` 增补 Agent 角色与工具使用约定。
- **扩展** `src/furflycode/tui/`：`app.py` 接收并持有 `registry`、新增执行中工具成员；`stream.py` 的 `submit` 改走 `Agent.run`，事件消费 task 分派工具事件；`view.py` 新增 `tool_line`/`tool_result_summary` 渲染与执行指示。
- **扩展** `src/furflycode/cli.py`：构造 `new_default_registry()` 并注入 `FurflyCodeApp`。
- **新增测试** `tests/test_tool.py`（注册中心 + 各工具单测）、`tests/test_agent.py`（fake provider 驱动单轮闭环）。
- **依赖**：无新增外部依赖（`anthropic`/`openai`/`textual`/`rich`/`pyyaml` 已在 `pyproject.toml`）；开发依赖加 `pytest-asyncio`。配置 `.furflycode/config.yaml` 与 step1 完全一致，跨章节不变。
