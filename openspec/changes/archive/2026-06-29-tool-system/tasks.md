## 1. 扩展 llm 协议无关类型

- [x] 1.1 在 `src/furflycode/llm/__init__.py` 新增常量 `ROLE_TOOL = "tool"`（并把字面量 `"user"`/`"assistant"` 提为 `ROLE_USER`/`ROLE_ASSISTANT`）。
- [x] 1.2 新增 dataclass：`ToolCall(id, name, input)`、`ToolResult(tool_call_id, content, is_error=False)`、`ToolDefinition(name, description, input_schema)`，各带中文 docstring。
- [x] 1.3 给 `Message` 增字段 `tool_calls`/`tool_results`（均 `field(default_factory=list)`），`role` 扩展为 `Literal["user","assistant","tool"]`，`content` 给默认值 `""`；给 `StreamEvent` 增字段 `tool_calls` 并更新四态语义 docstring。
- [x] 1.4 验证：`python -c "from furflycode.llm import ToolCall, ToolResult, ToolDefinition, ROLE_TOOL, Message, StreamEvent; print(Message(role='tool').tool_results)"` 输出 `[]`；`ruff check src/furflycode/llm/__init__.py` 无告警。

## 2. tool 包骨架

- [x] 2.1 在 `src/furflycode/tool/__init__.py` 定义 `@dataclass class Result(content: str, is_error: bool = False)`。
- [x] 2.2 定义 `@runtime_checkable class Tool(Protocol)`：`name()`/`description()`/`parameters()`/`async def execute(self, args: str) -> Result`。
- [x] 2.3 定义 `_truncate(s, max_lines, max_chars)`：超出尾部追加 `\n[truncated]` 标注。
- [x] 2.4 定义 `class Registry`：`register(t)`（重复名抛 `ValueError`）、`get(name)`、`definitions() -> list[ToolDefinition]`（按 `_order` 有序）、`async def execute(self, name, args, timeout=DEFAULT_TIMEOUT) -> Result`（未知工具兜底 `is_error`；`asyncio.wait_for` 超时转 `Result`；异常转 `Result`）。
- [x] 2.5 常量 `DEFAULT_TIMEOUT: float = 30.0`（暂不写 `new_default_registry`）。验证 `Registry().definitions()` 输出 `[]`。

## 3. 六个核心工具

- [x] 3.1 在 `src/furflycode/tool/read_file.py` 实现 `ReadFileTool`：`parameters()` 返回 `path` 必填 schema；`execute` 空 args 归一 `"{}"`，`is_dir()`/不存在/`PermissionError` 返回 `is_error`，成功按 `f"{n:6d}\t{line}"` 加行号，经 `_truncate` 限 2000 行/256KB。
- [x] 3.2 在 `src/furflycode/tool/write_file.py` 实现 `WriteFileTool`：`path`/`content` 必填；`Path(path).parent.mkdir(parents=True, exist_ok=True)` 后 `write_text` 覆盖；成功返回路径与字节数；`OSError` 返回 `is_error`。
- [x] 3.3 在 `src/furflycode/tool/edit_file.py` 实现 `EditFileTool`：`path`/`old_string`/`new_string` 必填；`n=content.count(old)`，`n==0` 返回「未找到匹配」，`n>1` 返回含 N 的唯一性错误，`n==1` 替换写回。
- [x] 3.4 在 `src/furflycode/tool/bash.py` 实现 `BashTool`：`command` 必填；`asyncio.create_subprocess_shell(cmd, stdout=PIPE, stderr=PIPE)` + `communicate()`；组装 `exit_code/stdout/stderr` 经 `_truncate(max_lines=10000, max_chars=30000)`；非零退出不设 `is_error`（超时由 Registry 捕获）。
- [x] 3.5 在 `src/furflycode/tool/glob_tool.py` 实现 `GlobTool`：`pattern` 必填、`path` 可选默认 `.`；`root.glob(pattern)` 过滤文件、`sorted` 取前 100；循环中每 100 个 `await asyncio.sleep(0)`；无匹配返回 `Result(content="无匹配")`（非 `is_error`）。
- [x] 3.6 在 `src/furflycode/tool/grep_tool.py` 实现 `GrepTool`：`pattern` 必填（Python 正则）、`path`/`glob` 可选；`re.compile` 失败返回 `is_error`；`root.rglob` 遍历逐行匹配收集 `file:line:content`（≤100，超出标注）；`OSError`/`UnicodeDecodeError` 跳过；超长行标注「未完整搜索」；无命中返回 `Result(content="无命中")`（非 `is_error`）。

## 4. new_default_registry 与 tool 单测

- [x] 4.1 在 `src/furflycode/tool/__init__.py` 增 `new_default_registry()`：依次 `register` 6 个工具返回 `Registry`。
- [x] 4.2 在 `tests/test_tool.py`（pytest-asyncio）测：`definitions()` 恰好 6 条且名称有序；`read_file` 存在/不存在；`write_file` 新建 + 嵌套路径（`tmp_path` fixture）检查磁盘；`edit_file` 0/1/多三情形错误可区分；`bash` `echo` 与超时（注入极短 timeout 跑 `sleep 5`）；`glob` `**/*.py`；`grep` 关键字。
- [x] 4.3 若未装 pytest-asyncio：`pyproject.toml` 的 `[dependency-groups].dev` 加 `pytest-asyncio>=0.23`，`[tool.pytest.ini_options]` 加 `asyncio_mode = "auto"`。验证 `pytest tests/test_tool.py -v` 全通过。

## 5. Provider.stream 注入工具定义

- [x] 5.1 在 `src/furflycode/llm/__init__.py` 把 `Provider.stream` 签名改为 `stream(self, msgs, tools: list[ToolDefinition]) -> AsyncIterator[StreamEvent]`，更新 Protocol docstring。
- [x] 5.2 在 `anthropic_provider.py` 加 `tools` 形参，新增 `_to_anthropic_tools(tools)` 转 `[{"name","description","input_schema"}]` 入参（流解析暂不变）。
- [x] 5.3 在 `openai_provider.py` 加 `tools` 形参，新增 `_to_openai_tools(tools)` 转 `[{"type":"function","function":{"name","description","parameters"}}]` 入参。
- [x] 5.4 在 `tui/stream.py` 把 `provider.stream(conv.messages())` 暂改为传 `[]` 第二参数（T8 会替换为 `Agent.run`）。验证 `python -m furflycode` 发纯文本仍正常。

## 6. anthropic 适配器解析工具调用与回灌

- [x] 6.1 在 `anthropic_provider.py` 流循环改用 `async with self._client.messages.stream(**params) as stream: async for event in stream:`；`content_block_delta` + `text_delta` → `yield StreamEvent(text=...)`；`thinking_delta`/`input_json_delta` 跳过。
- [x] 6.2 流结束后 `final_message = await stream.get_final_message()`；若 `stop_reason == "tool_use"`，遍历 `final_message.content` 对 `ToolUseBlock` 收集 `ToolCall(id, name, input=json.dumps(block.input))`，非空则 `yield StreamEvent(tool_calls=calls)`，随后 `yield StreamEvent(done=True)`。
- [x] 6.3 扩展 `_to_anthropic_messages`：assistant 有 `tool_calls` 时 content 用 `[{"type":"text","text":preamble}] + [{"type":"tool_use","id","name","input":json.loads(c.input)}]`；`ROLE_TOOL` 把每个 `ToolResult` 用 `{"type":"tool_result","tool_use_id","content","is_error"}` 拼进一条 `{"role":"user","content":[...]}`。
- [x] 6.4 含工具历史的请求关闭 thinking（`msgs` 存在 `tool_results` 或 assistant `tool_calls` 时 params 不加 `thinking`，避免 400）。验证 `python -m furflycode` 启动正常、`ruff check` 无告警。

## 7. openai 适配器解析工具调用与回灌

- [x] 7.1 在 `openai_provider.py` 流循环维护 `tool_calls_buf: dict[int, dict[str,str]]`（按 `delta.tool_calls[i].index` 累加 id/name/arguments 拼接）；正文 `delta.content` 仍 `yield StreamEvent(text=...)`。
- [x] 7.2 流结束后（`finish_reason == "tool_calls"` 或 buf 非空）按 index 排序组 `ToolCall(id, name, input=v.get("args") or "{}")`，`yield StreamEvent(tool_calls=calls)` 再 `yield StreamEvent(done=True)`。
- [x] 7.3 扩展 `_to_openai_messages`：assistant 有 `tool_calls` 时发 `{"role":"assistant","content":preamble or None,"tool_calls":[{"id","type":"function","function":{"name","arguments":c.input or "{}"}}]}`；`ROLE_TOOL` 每个 `ToolResult` 发一条 `{"role":"tool","tool_call_id","content"}`。验证 `python -m furflycode` 启动正常、`ruff check` 无告警。

## 8. conversation 扩展

- [x] 8.1 在 `src/furflycode/conversation.py` 新增 `add_assistant_with_tool_calls(self, text, calls)`：追加 `Message(role=ROLE_ASSISTANT, content=text, tool_calls=list(calls))`。
- [x] 8.2 新增 `add_tool_results(self, results)`：追加 `Message(role=ROLE_TOOL, tool_results=list(results))`。保留现有方法不变。
- [x] 8.3 在 `tests/test_conversation.py` 补断言：依次 `add_user`/`add_assistant_with_tool_calls`/`add_tool_results`/`add_assistant` 后 `messages()` 长度=4、role 序列正确、`tool_calls`/`tool_results` 内容正确。验证 `pytest tests/test_conversation.py -v` 通过。

## 9. agent 单轮闭环

- [x] 9.1 在 `src/furflycode/agent/__init__.py` 定义 `Phase`(START/END)、`ToolEvent`、`Event`、`class Agent(provider, registry)`、`async def run(self, conv) -> AsyncIterator[Event]`（按 plan 的 run 算法）；`_stream_once(conv, defs)` 内部 helper 转发 text、累积 preamble、收集 tool_calls；args 预览取 `input` 简短串（截断到 80 字符）。
- [x] 9.2 在 `tests/test_agent.py`（pytest-asyncio）用 `FakeProvider`（实现 Provider Protocol，内部用 `call_count` 切换两段脚本）编排：(a) 请求#1 yield 1 个 `read_file` ToolCall、请求#2 yield 文本「文件已读取」→ 断言 Event 序列含 `tool=START/END` 与最终 `text`、`conv.messages()` 末尾为 assistant 文本；(b) 请求#1 yield 工具、请求#2 仍 yield 工具 → 断言只调用一次 `registry.execute`、不再触发执行（单轮闭环约束）。验证 `pytest tests/test_agent.py -v` 全通过。

## 10. prompt 系统提示词扩展

- [x] 10.1 在 `src/furflycode/prompt.py` 扩写 `SYSTEM_PROMPT`：说明 FurflyCode 是能使用工具的 Agent，可读写改文件、执行命令、查找/搜索代码；需要信息或操作时调用相应工具，拿到结果后给出简洁答复。验证 `ruff check` 无告警、`pytest` 不回归。

## 11. tui 接入 agent 与工具行渲染

- [x] 11.1 在 `tui/app.py`：`FurflyCodeApp.__init__(self, providers, version, registry)` 存 `self._registry`；新增成员 `self._cur_tool: ToolDisplay | None = None`（小 dataclass：`name`/`args`）。
- [x] 11.2 在 `tui/stream.py`：`submit` 走 `self._stream_task = asyncio.create_task(self._consume_agent_events())`（替换临时 `_consume_stream`）；内部构造 `agent = Agent(self.provider, self._registry)` 后 `async for ev in agent.run(self.conv):` 分派。
- [x] 11.3 `_consume_agent_events` 分派：`ev.text` → `cur_reply += ev.text` 刷新动态区；`ev.tool`+`START` → 若 `cur_reply` 非空先 `RichLog.write(Markdown(cur_reply))` 提交 preamble 并清空，置 `self._cur_tool`；`ev.tool`+`END` → `RichLog.write(tool_line(name,args))` 紧接 `RichLog.write(tool_result_summary(result,is_error))`，清 `self._cur_tool`；`ev.done` → 把 `cur_reply` 经 markdown 渲染写入 `RichLog` 后 `_finish_turn()`；`ev.err` → `RichLog.write(error_block(err))` 后 `_finish_turn()`。
- [x] 11.4 在 `tui/view.py` 新增：`tool_line(name, args) -> RenderableType`（`Text("● ", style="bold cyan") + Text(f"{name}({args})", style="bold")`）、`tool_result_summary(result, is_error) -> RenderableType`（`Padding(Text("⎿ " + result, style="red" if is_error else "dim"), (0,0,0,2))`，UI 截断 ~8 行）；`_render_streaming` 在 `self._cur_tool is not None` 时渲染 `f"● {name}({args}) Running…"` + spinner，否则沿用 `Imagining… (Ns)`。验证 `python -m furflycode` 启动正常、`ruff check src/furflycode/tui/` 无告警。

## 12. cli 接线

- [x] 12.1 在 `src/furflycode/cli.py` `from furflycode.tool import new_default_registry`；构造 `registry = new_default_registry()`；`FurflyCodeApp(cfg.providers, __version__, registry).run()`。验证 `python -m furflycode` 在合法配置下能启动 TUI 并进入对话。

## 13. 验证

- [x] 13.1 `ruff format --check .` 与 `ruff check .` 无告警。
- [x] 13.2 `pytest -v` 通过（`tests/test_config.py`、`tests/test_conversation.py`、`tests/test_tool.py`、`tests/test_agent.py`）。
- [x] 13.3 （可选）`mypy src/furflycode` 通过（可选项，未完成不阻塞）。
- [x] 13.4 端到端冒烟：用 openai 兼容端点问「读 `openspec/changes/archive/2026-06-29-tool-system/specs/tool-system/spec.md` 并用一句话总结」→ 观察工具行 `● read_file(...)` + 结果摘要 + 最终答复。
- [x] 13.5 错误恢复：读不存在文件、edit 匹配不到、bash 非零退出 → 错误结构化回灌、程序不退出。
- [x] 13.6 （可选）若有 anthropic 配置，重复冒烟验证跨协议一致。
- [x] 13.7 用 tmux 验证 scrollback：完成块可回看工具行 + 结果摘要 + 最终答复，顺序不乱。
- [x] 13.8 密钥不回显/不打印：对话区与任何输出均不出现 `api_key`（通读运行输出、检索无明文 key）。
