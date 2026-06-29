# CLAUDE.md
## 1. Project Overview
我正在构建一个终端 AI 编程助手（类似 Claude Code），项目名叫 Furfly Code，使用 Python 实现。​
​
## 2. Commands
- 安装依赖：`uv sync`
- 运行 TUI：`uv run furflycode` 或 `uv run python -m furflycode`
- 测试：`uv run pytest`
- Lint：`uv run ruff check src/ tests/`
- 格式化：`uv run ruff format src/ tests/`
- 配置：复制 `.furflycode/config.yaml.example` 为 `.furflycode/config.yaml` 并填入密钥

## 3. Architecture
分层架构，源码在 `src/furflycode/`：
- `cli.py` 入口：加载配置 → 启动 TUI。
- `config.py` 配置层：读取并校验 `.furflycode/config.yaml`，产出 providers 列表。
- `llm/` 协议层：`Provider` Protocol + `Message`/`StreamEvent` 类型 + `new_provider` 工厂；
  `anthropic_provider.py`、`openai_provider.py` 封装官方 SDK 流式调用，统一吐出文本增量（思考增量丢弃）。
- `conversation.py` 会话层：进程内多轮历史。
- `prompt.py` 内置 system prompt 与 ASCII 猫 banner。
- `tui/` 终端层：`app.py`（状态机 SELECTING/IDLE/STREAMING + App）、`stream.py`（流式消费 + 计时）、
  `select.py`（provider 选择 OptionList）、`view.py`（渲染拼装：状态栏/错误/markdown 定型）。
- 数据流：用户输入 → conversation 追加 → `provider.stream(msgs)` async generator → TUI async task 逐事件消费 →
  完成时 Rich Markdown 渲染追加到 RichLog → conversation 追加 assistant → 回 IDLE。

## 4. Conventions
- 强制要求中文回答，中文注释。
- 分支策略：直接在 main 上开发。
- Commit message 风格：建议用约定式提交 feat fix docs refactor chore 
- 格式：<类型>: <描述>，中文描述。第一行 ≤50 字，必要时空一行写正文说明 why。
## 5. Hard Constraints

## 6. Gotchas
