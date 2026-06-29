# refactor-tool-types

## Why

step2 工具系统已验收，但 `tool` 数据结构有两层"乱"：

1. **类型住错地方（依赖方向倒）**：协议无关的共享类型（`Message`/`StreamEvent`/`ToolCall`/`ToolResult`/`ToolDefinition`/`ROLE_*`/`dumps_tool_input`）全堆在 `llm/` 里——它们自己的文档都自称"协议无关"，却住在一个叫 `llm` 的包里。这逼着 `tool/`（文档自称"零外部依赖，不感知 LLM 协议"，却在 `tool/__init__.py:13` `from furflycode.llm import ToolDefinition`）和 `conversation.py`、`agent` 全部反向依赖 `llm/`。`llm/` 一身两职：既是 LLM 适配器，又当全工程共享词汇库。
2. **每个工具重复样板**：6 个工具各写"解析 JSON → 取参 → 缺参检查"三件套；共享的 `_parse_args` 寄居叶子工具 `read_file.py:68` 被另外 5 个反向导入；返回 `dict | Result` 联合类型逼出每处 `isinstance(data, Result)` 判空；schema 的 `required` 与手写缺参检查两处事实源。

## What Changes

- **Part 1 类型归位（修依赖方向）**：新建 `src/furflycode/message.py`，从 `llm/__init__.py` 原样搬入 `Message`/`StreamEvent`/`ToolCall`/`ToolResult`/`ROLE_USER/ASSISTANT/TOOL`/`dumps_tool_input`；`ToolDefinition` 从 `llm` 搬入 `tool/__init__.py` 本地定义（删 `tool/__init__.py:13` 反向导入，使 `tool/` 零 furflycode 依赖）；`conversation.py`、`llm/__init__.py`、`anthropic_provider.py`、`openai_provider.py`、`agent/__init__.py`、两处测试的导入改向 `message`/`tool`，`Registry.definitions()` 返回本地 `ToolDefinition`。
- **Part 2 BaseTool 收口样板（tool/ 内部）**：在 `tool/__init__.py` 新增 `ToolInputError(ValueError)` 与 `BaseTool(ABC)`（抽象 `name/description/parameters/run`、具体 `execute` 模板），`_parse_args` 从 `read_file.py` 迁入此处并改签名 `_parse_args(args: str) -> dict[str, Any]`、失败抛 `ToolInputError`；6 个工具（`read_file`/`write_file`/`edit_file`/`bash`/`glob_tool`/`grep_tool`）继承 `BaseTool`、`execute`→`run(self, args: dict)`、删 `_parse_args`+`isinstance` 前导与反向导入、删纯 null 检查（保留空串/业务校验）。

## Capabilities

### New Capabilities

<!-- 留空：纯内部重构，无新 capability -->

### Modified Capabilities

<!-- 留空：行为零变化，不改任何 spec 级需求。step3 落在 step2 spec F1/F5/F9/N4 内，不改 spec 与验收标准 -->

## Impact

受影响文件：

- 新建 `src/furflycode/message.py`。
- `src/furflycode/tool/__init__.py` —— 本地定义 `ToolDefinition`、新增 `BaseTool`/`ToolInputError`、迁入 `_parse_args`；`Tool`/`Registry`/`Result`/`_truncate` 不变。
- `src/furflycode/tool/{read_file,write_file,edit_file,bash,glob_tool,grep_tool}.py` —— 继承 `BaseTool`、`execute`→`run`、删前导与反向导入与纯 null 检查。
- `src/furflycode/llm/__init__.py` —— 瘦身为 `Provider`+`new_provider`，从 message/tool 取类型。
- `src/furflycode/llm/{anthropic_provider,openai_provider}.py` —— 共享类型改从 message+tool 导入。
- `src/furflycode/conversation.py`、`src/furflycode/agent/__init__.py` —— 导入路径改向 message。
- `tests/test_conversation.py`、`tests/test_agent.py` —— 导入路径改向 message/tool，断言不动。
