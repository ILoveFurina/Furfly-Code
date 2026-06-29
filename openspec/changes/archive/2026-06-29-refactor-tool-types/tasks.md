# Tasks — refactor-tool-types

## 1. 类型归位（Part 1：修依赖方向）

- [x] 1.1 新建 `src/furflycode/message.py`：从 `llm/__init__.py` 原样搬入 `Message`、`StreamEvent`、`ToolCall`、`ToolResult`、`ROLE_USER/ASSISTANT/TOOL`、`dumps_tool_input`（含文档字符串与 `__all__`），仅依赖 `json`/`dataclasses`/`typing`。
- [x] 1.2 `src/furflycode/tool/__init__.py`：把 `ToolDefinition` 从 `llm` 搬来本地定义，删 `from furflycode.llm import ToolDefinition`（line 13），使 `tool/` 零 furflycode 依赖；`Registry.definitions()` 返回本地 `ToolDefinition`。
- [x] 1.3 `src/furflycode/conversation.py`：`from furflycode.llm import (...)`（line 5-12）改为 `from furflycode.message import ROLE_ASSISTANT, ROLE_TOOL, ROLE_USER, Message, ToolCall, ToolResult`；`Conversation` 类不动。
- [x] 1.4 `src/furflycode/llm/__init__.py`：只留 `Provider` Protocol + `new_provider` + `from furflycode.config import ProviderConfig`；`Provider.stream` 签名加 `from furflycode.message import Message, StreamEvent` 与 `from furflycode.tool import ToolDefinition`；`__all__` 缩为 `["Provider", "new_provider"]`。
- [x] 1.5 `src/furflycode/llm/anthropic_provider.py`、`openai_provider.py`：把 `from furflycode.llm import (ROLE_*, Message, StreamEvent, ToolCall, ToolDefinition[, dumps_tool_input])` 拆为 `from furflycode.message import ...` + `from furflycode.tool import ToolDefinition`；其余（`SYSTEM_PROMPT`、`config` TYPE_CHECKING、stream 实现）不动。
- [x] 1.6 `src/furflycode/agent/__init__.py`：`from furflycode.llm import Provider, ToolCall, ToolResult`（line 15）拆为 `from furflycode.llm import Provider` + `from furflycode.message import ToolCall, ToolResult`。
- [x] 1.7 `tests/test_conversation.py:6` → `from furflycode.message import ToolCall, ToolResult`；`tests/test_agent.py:10` → `from furflycode.message import StreamEvent, ToolCall` + `from furflycode.tool import ToolDefinition`；仅改导入路径，断言不动。

## 2. BaseTool 收口（Part 2：tool/ 内部）

- [x] 2.1 `src/furflycode/tool/__init__.py`：保留 `Tool` Protocol（`@runtime_checkable`，`Registry` 注解 `dict[str, Tool]` 不变）。
- [x] 2.2 `src/furflycode/tool/__init__.py`：新增 `ToolInputError(ValueError)`。
- [x] 2.3 `src/furflycode/tool/__init__.py`：`_parse_args` 从 `read_file.py` 移入此处，签名改 `_parse_args(args: str) -> dict[str, Any]`，失败抛 `ToolInputError`（消息文案不变：`参数 JSON 解析失败: …` / `参数必须是 JSON 对象`）。
- [x] 2.4 `src/furflycode/tool/__init__.py`：新增 `BaseTool(ABC)`——抽象 `name/description/parameters/run(self, args: dict[str, Any]) -> Result`；具体 `execute(self, args: str) -> Result` 模板 = `try _parse_args except ToolInputError → Result(is_error=True, content=str(e))` → 按 `self.parameters().get("required", [])` 校验 `data.get(key) is None` 返回 `缺少必填参数: {key}` → `return await self.run(data)`。
- [x] 2.5 `read_file.py`：继承 `BaseTool`、`execute`→`run(self, args: dict)`、删 `_parse_args`+`isinstance` 前导与反向导入。
- [x] 2.6 `write_file.py`：继承 `BaseTool`、`execute`→`run`、删前导与反向导入；删纯 null 检查 `if content is None`，保留空串值校验。
- [x] 2.7 `edit_file.py`：继承 `BaseTool`、`execute`→`run`、删前导与反向导入；删纯 null 检查 `if old_string is None`/`if new_string is None`，保留匹配数等业务校验。
- [x] 2.8 `bash.py`：继承 `BaseTool`、`execute`→`run`、删前导与反向导入。
- [x] 2.9 `glob_tool.py`：继承 `BaseTool`、`execute`→`run`、删前导与反向导入。
- [x] 2.10 `grep_tool.py`：继承 `BaseTool`、`execute`→`run`、删前导与反向导入；保留正则编译等值校验。

## 3. 验证

- [x] 3.1 `uv run ruff check src/ tests/` 与 `uv run ruff format --check src/ tests/` 通过。
- [x] 3.2 导入健康（验无环、路径全通）：`uv run python -c "import furflycode.tool, furflycode.message, furflycode.conversation, furflycode.llm, furflycode.agent, furflycode.tui.app"` 无报错。
- [x] 3.3 `uv run pytest -q` 全绿（全量跑，因导入路径变了；重点看 test_tool/test_agent/test_conversation）。
- [x] 3.4 冒烟：`uv run python -c "from furflycode.tool import new_default_registry; r=new_default_registry(); print([d.name for d in r.definitions()])"` 输出 `['read_file','write_file','edit_file','bash','glob','grep']`。
- [x] 3.5 抽查读文件与缺参：`uv run python -c "import asyncio,json; from furflycode.tool.read_file import ReadFileTool; t=ReadFileTool(); print(asyncio.run(t.execute(json.dumps({'path':'pyproject.toml'})))[:40]); print(asyncio.run(t.execute(json.dumps({}))).content)"`——前者读到带行号内容，后者输出 `缺少必填参数: path`。
- [x] 3.6 可选 mypy：`uv run mypy src/furflycode`（项目把 mypy 列为可选项，非必须）。
