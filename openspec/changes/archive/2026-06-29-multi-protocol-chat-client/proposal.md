## Why

furflycode 是从零构建的 Claude Code 风格终端 AI Agent，在引入工具调用、权限、记忆等高级能力之前，需要先打通"人 ↔ LLM"的最小闭环。本 change 是整个项目的第一块基石：让用户能在终端里与大模型进行流畅的多轮对话，同时通过一份配置切换 Anthropic 与 OpenAI 两种协议（含兼容端点）。现在做是因为后续的工具系统、Agent 闭环都依赖这一层稳定的对话与流式基础设施。

## What Changes

- 新增 YAML 配置加载与校验：从 `.furflycode/config.yaml` 读取 providers 列表（可读名称、协议类型、可选自定义端点、密钥、模型名、是否开启扩展思考），缺失必要项时给出清晰启动期错误并终止。
- 新增多协议适配层：定义协议无关的 `Provider` Protocol + 统一 `Message`/`StreamEvent` 类型，封装 `anthropic` 与 `openai` 官方 SDK 的 async 流式调用，统一吐出文本增量（思考增量内部丢弃）。
- 新增 provider 选择：单份配置直进对话，多份配置启动后呈现方向键选择列表，选定者即本次会话活动 provider。
- 新增会话层：进程内维护单会话多轮历史（user/assistant 交替），每轮请求携带此前全部上下文。
- 新增全功能 TUI（基于 Textual + Rich）：启动横幅（ASCII 猫 + 应用名版本 + 工作目录）、就绪提示行、对话区、带边框输入框（含 ❯ 与占位符）、底部状态栏（左 provider 名、右模型名）。
- 新增流式呈现与渲染：流式期间纯文本逐字实时显示，本轮结束后用 `rich.markdown.Markdown` 整段定型美化（代码块、列表、强调）。
- 新增输入与提交：输入框支持 Alt+Enter 多行编辑、Enter 提交，提交后清空并进入等待/流式状态，期间不接受新提交。
- 新增退出：`/exit` 命令或 Ctrl+C 均可安全退出并恢复终端状态。
- 新增错误反馈：请求失败（鉴权、限流、网络、模型不存在等）在对话区以可区分样式显示，不退出会话。
- 新增响应计时：自请求发出即启动计时，"进行中"指示实时显示已用秒数（形如 `Imagining… (5s)`），结束后定型显示总耗时。
- 新增非阻塞流式：网络请求与界面渲染互不阻塞，等待与流式期间界面保持响应。

## Capabilities

### New Capabilities
- `chat-client`: 终端多协议 LLM 对话客户端的配置加载、多协议适配、多轮上下文、全功能 TUI、流式渲染、错误反馈与计时

### Modified Capabilities
<!-- 无既有 capability 修改 -->

## Impact

- 新增项目骨架与入口：`pyproject.toml`（依赖 textual、rich、anthropic、openai、pyyaml，脚本入口 `furflycode = "furflycode.cli:main"`）、`src/furflycode/__init__.py`、`src/furflycode/__main__.py`、`src/furflycode/cli.py`。
- 新增配置层：`src/furflycode/config.py`（`Config`/`ProviderConfig`/`ConfigError`/`load`）。
- 新增配置模板与忽略：`.furflycode/config.yaml.example`、`.gitignore` 追加 `.furflycode/config.yaml`。
- 新增提示词资源：`src/furflycode/prompt.py`（`SYSTEM_PROMPT`、`CAT_BANNER`、`render_banner`）。
- 新增 LLM 协议层：`src/furflycode/llm/__init__.py`（`Provider` Protocol、`Message`、`StreamEvent`、`new_provider` 工厂）、`src/furflycode/llm/anthropic_provider.py`、`src/furflycode/llm/openai_provider.py`。
- 新增会话层：`src/furflycode/conversation.py`。
- 新增终端层：`src/furflycode/tui/app.py`、`src/furflycode/tui/stream.py`、`src/furflycode/tui/select.py`、`src/furflycode/tui/view.py`。
- 新增依赖：`textual`、`rich`、`anthropic`、`openai`、`pyyaml`；开发依赖 `pytest`、`ruff`、`mypy`。
- 新增测试：`tests/test_config.py`、`tests/test_conversation.py`。
