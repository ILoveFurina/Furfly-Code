# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 1. Project Overview
Furfly Code 是一个终端 AI 编程助手（Claude Code 风格），Python 实现，支持 Anthropic / OpenAI 多协议 LLM，带工具调用与流式 TUI。

## 2. Commands
- 安装依赖：`uv sync`
- 运行 TUI：`uv run furflycode` 或 `uv run python -m furflycode`
- 测试：`uv run pytest`（单个：`uv run pytest tests/test_tool.py::test_name`）
- Lint：`uv run ruff check src/ tests/`
- 格式化：`uv run ruff format src/ tests/`
- 类型检查：`uv run mypy src/`
- 配置：复制 `.furflycode/config.yaml.example` 为 `.furflycode/config.yaml` 并填入密钥

## 3. Architecture
分层架构，源码在 `src/furflycode/`，依赖方向严格自顶向下：

- `message.py` — 协议无关传输词汇（`Message`/`ToolCall`/`ToolResult`/`StreamEvent`/`ROLE_*`）。中性叶子模块，任何层可依赖而不引入方向倒置。
- `config.py` — 加载校验 `.furflycode/config.yaml`，产出 `ProviderConfig`/`Config`。
- `tool/` — `BaseTool` ABC + `Registry` + `ToolDefinition` + `Result`。零内部依赖、不感知 LLM 协议。`new_default_registry()` 注册 6 个内置工具：read/write/edit_file、bash、glob、grep。
- `llm/` — `Provider` Protocol（runtime_checkable）+ `new_provider()` 工厂按 `protocol` 字段分发到 `anthropic_provider`/`openai_provider`。适配器在边界把协议无关 `Message` 转成各家 API 形状。
- `agent/` — `Agent` 单轮闭环编排：请求#1（带工具）→ 收集 `tool_calls` → `Registry` 顺序执行 → 结果回灌 `Conversation` → 请求#2（续答）。对外吐 `Event` async generator。**不 import anthropic/openai**，只依赖 `Provider` 接口。
- `tui/` — Textual 应用：`app.py`（`furflycodeApp` + `PromptInput` + `SessionState` 状态机）、`stream.py`（消费 agent 事件流渲染）、`view.py`（渲染函数）、`select.py`（provider 选择）。
- `cli.py` — 入口：`load` config → `new_default_registry()` → `furflycodeApp(providers, registry).run()`。

### 关键设计
- **Provider 适配器模式**：`agent`/`tui` 只依赖 `llm.Provider` Protocol；新增协议只需实现接口并在 `new_provider` 注册。
- **工具结果回灌形状**（`anthropic_provider._to_anthropic_messages`）：ROLE_TOOL 回合映射为一条 user 消息的 `tool_result` 块数组；assistant 工具调用回合 content 用 `[text, tool_use...]` 数组。
- **thinking 与工具历史互斥**：含工具历史的请求关闭 thinking，避免签名缺失导致 400。
- **单轮上限**：续答请求#2 忽略其返回的工具调用，不再发起新一轮工具执行。
- **StreamEvent 四态**：text / tool_calls / done / err（err 与 done 互斥）。

## 4. Conventions
- 强制中文回答、中文注释。
- 分支策略：直接在 main 上开发。
- Commit 风格：约定式提交（feat/fix/docs/refactor/chore），中文描述，首行 ≤50 字，必要时空一行写正文说明 why。
- 工具失败一律包成 `Result(is_error=True)` 回灌，不抛 Python 异常给上层。

## 5. Hard Constraints
- `agent/` 不得 import `anthropic`/`openai`（协议无关）。
- `message.py`/`tool/` 保持零内部依赖、不绑定 LLM 协议。
- 工具执行不外抛异常：`BaseTool.execute` 解析/校验失败、`Registry.execute` 超时/异常均转为 `Result(is_error=True)`。

## 6. Gotchas
- `PromptInput._on_key` 必须是 `async def` 并 `await super()._on_key(event)`——父类 `Widget._on_key` 是 async，同步 override 会让「其他按键委托父类」失效（协程未被 await）。
- `mypy` 对同一作用域内带类型标注的重复声明报 `[no-redef]`（即便类型相同）；分支复用变量时只在一处加 `: T` 标注。
- `query_one("#id")` 不带类型参数返回 `Widget` 基类，访问 `write`/`update` 需显式传类型如 `query_one("#log", RichLog)`。
- 测试在 Windows 跑完会有 `PytestUnraisableExceptionWarning ... unclosed transport` 噪声（asyncio Proactor 清理），与代码无关，测试全过即可忽略。

## 7. Spec 驱动
项目用 openspec 做 spec-driven 开发（见 `openspec/`：specs 在 `openspec/specs/`，归档变更在 `openspec/changes/archive/`）。新功能/模块开发可用 `furfly-spec` 或 `openspec-*` skills 走 spec → plan → task → checklist 流程。
