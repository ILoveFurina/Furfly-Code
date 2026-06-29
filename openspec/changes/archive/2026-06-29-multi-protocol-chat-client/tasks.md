# 多协议 LLM 终端对话客户端 Tasks

> 包名：`furflycode`（Python 3.12+）。源码位于 `src/furflycode/`，内部模块以 `furflycode.xxx` 导入。本 change 已实现并提交，以下为 retroactive 任务清单。

## 1. 项目骨架与依赖

- [x] 1.1 用 `uv init` 或手写 `pyproject.toml`：`name = "furflycode"`、`version = "0.1.0"`、`requires-python = ">=3.12"`，依赖 `textual>=0.80`、`rich>=13`、`anthropic>=0.40`、`openai>=1.50`、`pyyaml>=6`；`[project.scripts] furflycode = "furflycode.cli:main"`；build-backend 用 hatchling、`packages = ["src/furflycode"]`；dev 依赖 `pytest>=8`、`ruff>=0.6`、`mypy>=1.10`。
- [x] 1.2 `src/furflycode/__init__.py`：定义 `__version__ = "0.1.0"`。
- [x] 1.3 `src/furflycode/__main__.py`：`from .cli import main; main()`，支持 `python -m furflycode`。
- [x] 1.4 `src/furflycode/cli.py` 写临时 `main()`，打印 `furflycode {__version__}` 确认可启动。
- [x] 1.5 安装依赖：`uv sync`（或 `pip install -e ".[dev]"`），`python -m furflycode` 能打印版本号。

## 2. config 模块

- [x] 2.1 在 `src/furflycode/config.py` 定义 `@dataclass ProviderConfig`（name、protocol、api_key、model、base_url: str | None = None、thinking: bool = False）与 `@dataclass Config(providers: list[ProviderConfig])`。
- [x] 2.2 定义 `class ConfigError(Exception)`。
- [x] 2.3 实现 `load(path) -> Config`：`pathlib.Path(path).read_text()` + `yaml.safe_load`，再调 `_from_dict` 手动映射到 dataclass 保留校验时机。
- [x] 2.4 校验：`providers` 非空；逐项 name/protocol/api_key/model 非空；`protocol ∈ {"anthropic", "openai"}`；失败抛 `ConfigError`，message 形如 `providers[1].api_key 不能为空`；文件不存在 → `ConfigError(f"配置文件不存在: {path}")`；YAML 解析失败 → 转 `ConfigError`。
- [x] 2.5 写 `tests/test_config.py`：合法配置返回正确条数；缺字段/非法 protocol/文件缺失分别抛 `ConfigError`。

## 3. 配置模板与忽略

- [x] 3.1 写 `.furflycode/config.yaml.example`：含 anthropic 条目（含 `thinking: true`）与一段注释掉的 openai 条目示例，字段与 `ProviderConfig` 对齐。
- [x] 3.2 `.gitignore` 追加 `.furflycode/config.yaml`。

## 4. prompt 模块

- [x] 4.1 在 `src/furflycode/prompt.py` 定义 `SYSTEM_PROMPT: str`（一段简洁固定 system prompt）。
- [x] 4.2 定义 `CAT_BANNER: str`（ASCII 猫：`/\_/\`、`( o.o )`、`> ^ <`）。
- [x] 4.3 实现 `render_banner(version, cwd) -> str`：拼出"猫 + furflycode vX + cwd + 就绪提示行"。

## 5. llm 包骨架

- [x] 5.1 在 `src/furflycode/llm/__init__.py` 定义 `@dataclass Message(role, content)` 与 `@dataclass StreamEvent(text="", done=False, err: Exception | None = None)`。
- [x] 5.2 定义 `class Provider(Protocol)`：`name`/`model`（property）；`def stream(self, msgs: list[Message]) -> AsyncIterator[StreamEvent]`。
- [x] 5.3 实现 `new_provider(cfg) -> Provider`：按 `cfg.protocol` 分派 `AnthropicProvider` / `OpenAIProvider`；未知协议抛 `ValueError`（适配器在 5/6 实现前用 try/except 占位让骨架可 import）。

## 6. conversation 模块

- [x] 6.1 在 `src/furflycode/conversation.py` 定义 `class Conversation`，内部 `self._messages: list[Message] = []`。
- [x] 6.2 实现 `add_user(text)`、`add_assistant(text)`、`messages() -> list[Message]`（返回 `list(self._messages)` 副本）。
- [x] 6.3 写 `tests/test_conversation.py`：连续 `add_user`/`add_assistant` 后 `messages()` 顺序与 role 正确。

## 7. anthropic 适配器

- [x] 7.1 在 `src/furflycode/llm/anthropic_provider.py` 定义 `class AnthropicProvider`：`__init__` 中 `self._client = anthropic.AsyncAnthropic(api_key=cfg.api_key, base_url=cfg.base_url or None)`；保存 model/name/thinking；`name`/`model` property 返回 cfg 对应字段。
- [x] 7.2 实现 `async def stream(msgs) -> AsyncIterator[StreamEvent]`：msgs 转 `[{"role": m.role, "content": m.content}]`；params 含 `model`/`max_tokens=4096`/`system=SYSTEM_PROMPT`/`messages`；若 thinking 加 `thinking={"type":"enabled","budget_tokens":2048}`。
- [x] 7.3 `try: async with self._client.messages.stream(**params) as stream: async for event in stream:` 判断 `event.type`：`content_block_delta` 且 `event.delta.type == "text_delta"` → `yield StreamEvent(text=event.delta.text)`；`thinking_delta` 跳过；其他忽略。
- [x] 7.4 `else` 正常结束 → `yield StreamEvent(done=True)`；`except asyncio.CancelledError: raise`；其他 `except Exception as e: yield StreamEvent(err=e)`。

## 8. openai 适配器

- [x] 8.1 在 `src/furflycode/llm/openai_provider.py` 定义 `class OpenAIProvider`：`__init__` 中 `self._client = openai.AsyncOpenAI(api_key=cfg.api_key, base_url=cfg.base_url or None)`；保存 model/name（thinking 忽略）；`name`/`model` property 同上。
- [x] 8.2 实现 `async def stream(msgs)`：组装 `messages = [{"role":"system","content": SYSTEM_PROMPT}] + [{"role": m.role,"content": m.content}]`。
- [x] 8.3 `try: stream = await self._client.chat.completions.create(model=self._model, messages=messages, stream=True)`；`async for chunk in stream:` 取 `chunk.choices[0].delta.content` 非空时 `yield StreamEvent(text=delta)`；结束 `yield StreamEvent(done=True)`。
- [x] 8.4 `except asyncio.CancelledError: raise`；其他 `except Exception as e: yield StreamEvent(err=e)`。

## 9. TUI App 骨架

- [x] 9.1 在 `src/furflycode/tui/app.py` 定义 `class SessionState(Enum)`：`SELECTING` / `IDLE` / `STREAMING`。
- [x] 9.2 定义 `class furflycodeApp(App)`：构造参数 `providers: list[ProviderConfig]`；初始化 state、`provider: Provider | None`、`conv = Conversation()`、`cur_reply = ""`、`turn_start = 0.0`、`_stream_task = None`、`_timer = None`。
- [x] 9.3 `compose()`：yield `RichLog`(id="log", wrap=True, markup=True)、`Static`(id="streaming")、`TextArea`(id="input", single_line=False)、`Static`(id="statusbar")。
- [x] 9.4 `on_mount`：把 `prompt.render_banner(__version__, os.getcwd())` 写进 `RichLog`；`len(providers) == 1` → `new_provider(providers[0])` + IDLE + 更新状态栏；否则切 SELECTING（在组 11 接入 OptionList）。
- [x] 9.5 `BINDINGS = [("ctrl+c", "quit", "Quit")]`；`async def action_quit`：若 `_stream_task` 存在则 `cancel()`，`self.exit()`。
- [x] 9.6 `cli.main` 调 `furflycodeApp(providers).run()`。

## 10. TUI 流式接入与计时

- [x] 10.1 给 `furflycodeApp` 添加 `async def submit(text)`：识别 `text.strip() == "/exit"` → `await self.action_quit()`；否则 `conv.add_user(text)`、`RichLog.write(user_block(text))`、清空 TextArea、`cur_reply = ""`、`turn_start = time.monotonic()`、切 STREAMING、`_stream_task = asyncio.create_task(self._consume_stream())`、`_timer = self.set_interval(0.1, self._tick)`。
- [x] 10.2 在 `src/furflycode/tui/stream.py` 实现 `async def _consume_stream`：`async for ev in self.provider.stream(self.conv.messages())`：`ev.err` → `_finish_with_error`；`ev.text` → `cur_reply += ev.text` + 刷新动态区；`ev.done` → `_finish_with_assistant`；外层 `except asyncio.CancelledError: raise`、其他 `except` → `_finish_with_error`。
- [x] 10.3 实现 `_tick`：仅 STREAMING 时刷新 `#streaming` 上的 `Imagining… ({int(elapsed)}s)`。
- [x] 10.4 实现 `_finish_with_assistant`：用 `rich.markdown.Markdown(reply)` 渲染 → `RichLog.write`；`conv.add_assistant(reply)`；`_timer.stop()`；`_stream_task = None`；回 IDLE；清空 `#streaming`。
- [x] 10.5 实现 `_finish_with_error`：`RichLog.write(error_block(e))`；回 IDLE。
- [x] 10.6 监听 TextArea 提交：Enter 提交、Alt+Enter 插入换行（用 binding + 自定义检查实现）。
- [x] 10.7 配真实 key 跑通一轮：可见 `Imagining… (Ns)` 计时、流式逐字、done 后 markdown 渲染追加到 RichLog。

## 11. TUI provider 选择

- [x] 11.1 在 `src/furflycode/tui/select.py`：`state == SELECTING` 时 `compose` 再 yield 一个 `OptionList`，列出 `f"{p.name} ({p.model})"` 每项。
- [x] 11.2 监听 `on_option_list_option_selected`：取对应 `ProviderConfig` → `self.provider = new_provider(cfg)` → 更新状态栏 → 隐藏/移除 OptionList → 切 IDLE。
- [x] 11.3 进入 SELECTING 时隐藏 TextArea/RichLog 仅显示 list，切回 IDLE 时反过来。
- [x] 11.4 用 2 条 provider 配置启动验证出现选择列表（端到端验证留到组 14）。

## 12. TUI View 拼装与渲染

- [x] 12.1 banner 在 `on_mount` 一次性写入 `RichLog`，不在每帧重绘。
- [x] 12.2 动态区仅 `#streaming`（流式时显示 `● {cur_reply}\nImagining… (Ns)`）+ 输入框 + 状态栏。
- [x] 12.3 状态栏：用 Rich `Text`/`Table.grid` 左 `provider.name`、右 `provider.model` 两端对齐，写到 `#statusbar: Static`。
- [x] 12.4 完成块：`user_block(text)` = `Text("● " + text, style="bold")`；`render_markdown(reply)` = `Group(Text("● "), Markdown(reply))`；都无 You/furflycode 文字标签。
- [x] 12.5 错误样式：`error_block(err)` 用 `Text("● " + str(err), style="bold red")`。
- [x] 12.6 长行：CSS 设 `#streaming: width: 1fr; height: auto;`、`Markdown`/`RichLog` 用 `width: 1fr;` 自适应（满足 N6）。

## 13. 入口装配

- [x] 13.1 在 `src/furflycode/cli.py` 替换占位实现 `def main()`：`try: cfg = config.load(".furflycode/config.yaml")`；`except ConfigError as e: print(e, file=sys.stderr); sys.exit(1)`。
- [x] 13.2 banner 交由 TUI 在 `on_mount` 写 `RichLog`（与占位保持一致）。
- [x] 13.3 `furflycodeApp(cfg.providers).run()`；非 KeyboardInterrupt 异常 `print(...)` 并 `sys.exit(1)`。
- [x] 13.4 验证合法配置下能启动 TUI，缺配置时打印可读错误且退出码非零。

## 14. 端到端联调

- [x] 14.1 用真实 anthropic 配置（`thinking: true`）跑：多轮对话、流式逐字、Imagining 计时、done 后 markdown 定型、思考内容不出现。
- [x] 14.2 用 openai 协议配置跑：同样多轮 + 流式。
- [x] 14.3 配两条 provider：启动出现选择列表，选定后状态栏正确。
- [x] 14.4 故意用错误 key：错误在对话区显示且不退出，可继续。
- [x] 14.5 `/exit` 与 Ctrl+C：安全退出、终端无残留（终端 raw mode 由 Textual 自动还原）。
- [x] 14.6 用 tmux 验证 scrollback 行为：完成块用终端原生滚轮 / Ctrl+B + `[` 可回看。

## 15. 验证

- [x] 15.1 `python -m furflycode` 能正常启动（在合法配置下进入 TUI）。
- [x] 15.2 `ruff check .` 无告警。
- [x] 15.3 `ruff format --check .` 通过（或本地 `ruff format .` 已统一格式）。
- [x] 15.4 `pytest` 通过（`tests/test_config.py`、`tests/test_conversation.py`）。
- [x] 15.5 （可选）`mypy src/furflycode` 通过（启用 strict 子集亦可）。
- [x] 15.6 密钥不回显/不打印：对话区与任何输出均不出现 `api_key` 明文（通读运行输出、检索无明文 key）。
