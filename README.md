# Furfly Code

终端里的 AI 编程助手。Python 实现，支持 Anthropic / OpenAI 多协议 LLM，带工具调用（读写文件、执行命令、搜索代码）与流式 TUI。inspired by Claude Code。

## 特性

- **多协议**：同一套对话接口适配 Anthropic 与 OpenAI（含兼容端点），切换配置即换后端。
- **工具调用**：6 个内置工具——`read_file` / `write_file` / `edit_file` / `bash` / `glob` / `grep`，模型自主调用并把结果回灌进上下文。
- **流式 TUI**：基于 Textual + Rich 的终端界面，逐字流式呈现、Markdown 渲染、工具行 `● name(args)` 风格展示。
- **扩展思考**：Anthropic 协议下可开启 thinking。

## 安装

需要 Python ≥ 3.12 与 [uv](https://docs.astral.sh/uv/)。

```bash
uv sync
```

## 用法

```bash
uv run furflycode
```

首次运行前复制配置模板并填入密钥：

```bash
cp .furflycode/config.yaml.example .furflycode/config.yaml
# 编辑 .furflycode/config.yaml，填入 api_key / model
```

## 配置

`.furflycode/config.yaml` 声明一个或多个 provider，每项含：名称、协议（`anthropic` / `openai`）、`api_key`、`model`、可选 `base_url`（兼容端点）、可选 `thinking`（仅 Anthropic 生效）。配置多个 provider 时，启动会出现方向键选择界面。

## 架构

分层架构，源码在 `src/furflycode/`，依赖严格自顶向下：

- `message.py` — 协议无关传输词汇（`Message` / `ToolCall` / `ToolResult` / `StreamEvent`）。
- `config.py` — 加载校验配置，产出 `Config`。
- `tool/` — `BaseTool` ABC + `Registry` + 6 个内置工具。
- `llm/` — `Provider` Protocol + `anthropic` / `openai` 适配器。
- `agent/` — 对话闭环编排，对外吐 `Event` 异步事件流。
- `tui/` — Textual 应用（渲染事件流、输入、状态）。
- `cli.py` — 入口。

新增 LLM 协议只需实现 `Provider` 接口并在工厂注册；`agent` / `tui` 不感知具体协议。

## 开发

```bash
uv run pytest               # 测试
uv run ruff check src/ tests/   # lint
uv run ruff format src/ tests/  # 格式化
uv run mypy src/             # 类型检查
```

本项目用 [openspec](https://github.com/fission-ai/openspec) 做 spec 驱动开发，spec 与变更记录见 `openspec/`。

## 许可证

MIT，见 [LICENSE](LICENSE)。
