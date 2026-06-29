# Design — refactor-tool-types

## Context

step2 工具系统已验收，但 `tool` 数据结构有两层"乱"：

1. **类型住错地方（依赖方向倒）**：协议无关的共享类型（`Message`/`StreamEvent`/`ToolCall`/`ToolResult`/`ToolDefinition`/`ROLE_*`/`dumps_tool_input`）全堆在 `llm/` 里——它们自己的文档都自称"协议无关"，却住在一个叫 `llm` 的包里。这逼着 `tool/`（文档自称"零外部依赖，不感知 LLM 协议"，却在 `tool/__init__.py:13` `from furflycode.llm import ToolDefinition`）和 `conversation.py`、`agent` 全部反向依赖 `llm/`。`llm/` 一身两职：既是 LLM 适配器，又当全工程共享词汇库。
2. **每个工具重复样板**：6 个工具各写"解析 JSON → 取参 → 缺参检查"三件套；共享的 `_parse_args` 寄居叶子工具 `read_file.py:68` 被另外 5 个反向导入；返回 `dict | Result` 联合类型逼出每处 `isinstance(data, Result)` 判空；schema 的 `required` 与手写缺参检查两处事实源。

**基线**：实施前用户已提交 WIP（commit `d416e64` "docs: 添加了一些个人思考的注释以及相关文档"），把会话开始时未提交的 `agent/__init__.py`、`cli.py`、`llm/__init__.py`、`anthropic_provider.py`、`grep_tool.py` 与文档落盘。工作区现仅 `conversation.py` 仍为未提交 M，但其内容与计划撰写时所读一致（已复核，无漂移）。从该基线开始实施，Part 1 会进一步改动 `conversation.py` 的导入行。

**目标布局**（无环；`tool`、`message` 为两个独立叶子）：

```
tool/        Tool, BaseTool, Result, ToolDefinition, Registry, _parse_args/_truncate   ← 零 furflycode 依赖
message.py   Message, StreamEvent, ToolCall, ToolResult, ROLE_*, dumps_tool_input       ← 仅 stdlib
conversation.py  Conversation（从 message 取类型）
llm/         Provider, new_provider, anthropic/openai_provider（从 message+tool 取类型）
agent        从 tool/message/conversation/llm 取类型
```

依赖方向：`llm→{tool,message}`、`conversation→message`、`agent→{tool,message,conversation,llm}`、`tui/cli` 不受影响（只碰 `Provider`/`Registry`/`Conversation`/`Agent`，归属不变）。

## Goals / Non-Goals

**Goals:**

- Part 1：修依赖方向——把共享词汇抽到中性 `message.py`、`ToolDefinition` 归 `tool/`，让 `tool/` 真正零 furflycode 依赖、兑现文档承诺。
- Part 2：引入 `BaseTool` 收口样板，建立单一事实源（schema 的 `required` 即缺参校验来源），消除 6 工具重复的解析/缺参三件套与反向导入。

**Non-Goals:**

- 行为零变化——落在 step2 spec F1/F5/F9/N4 内，不改 spec 与验收标准。
- 不改对外签名 `execute(args: str)`、`Registry.execute`、`definitions()`，agent/providers/conversation/tui 无需改（Part 1 已把 providers 的导入路径改掉）。

## Decisions

### D1：Protocol + BaseTool 结合（而非二选一）

沿用 `docs/questions/2026-06-27-protocol-vs-abc-design-choice.md` 的"Protocol + BaseXxx 结合"模式——该文档已写明"第二次复制同一段逻辑就抽 Base 基类"，工具层已第 6 次。`Tool` Protocol（`@runtime_checkable`）保留为对外形状契约，`Registry` 注解 `dict[str, Tool]` 不变；`BaseTool(ABC)` 收口样板供 6 工具继承。两者职责分离：Protocol 描述契约，ABC 复用实现。

### D2：`ToolDefinition` 归 `tool/` 而非 `message`

`ToolDefinition` 是工具 schema 形状，与 `tool/` 内聚，且让 `tool/` 兑现"零 furflycode 依赖"承诺的前提就是它本地定义。留在 `message.py` 反而让 `tool/` 仍需反向依赖。`message.py` 只收"消息/事件载荷"类（`Message`/`StreamEvent`/`ToolCall`/`ToolResult`/`ROLE_*`/`dumps_tool_input`）。

### D3：`_parse_args` 抛 `ToolInputError` 而非返回 Result

`_parse_args(args: str) -> dict[str, Any]` 失败抛 `ToolInputError(ValueError)`，由 `BaseTool.execute` 模板 `try/except` 捕获并转 `Result(is_error=True, content=str(e))`。这让 `_parse_args` 保持"纯解析"语义，错误处理收敛到基类一处；消息文案不变（`参数 JSON 解析失败: …` / `参数必须是 JSON 对象`）。

### D4：缺失/null 由基类兜，空串/业务校验留各工具 run

`BaseTool.execute` 模板流程：`try _parse_args except ToolInputError → Result(is_error=True)` → 按 `self.parameters().get("required", [])` 校验 `data.get(key) is None` 返回 `缺少必填参数: {key}` → `return await self.run(data)`。各工具 `run` 只保留值校验（`if not xxx` 空串、grep 正则编译、文件存在性、edit 匹配数等）——它们从"既挡缺失又挡空串"收敛为"只挡空串"，缺失/null 由基类兜。重构后职责划分：

| 关注点 | 归属 |
|---|---|
| JSON 解析 / 非 dict | `BaseTool.execute` + `_parse_args` |
| 必填键缺失 / null | `BaseTool.execute`（读 schema 的 `required`，单一事实源） |
| 空串 / 格式 / 业务校验 | 各工具 `run` |
| 超时 / 兜底异常 | `Registry.execute`（不变） |

## Risks / Trade-offs

- **兼容性风险**：行为零变化是硬约束，消息文案需逐字一致（缺失必填键、null、坏 JSON、非对象、空串必填值）。缓解——`_parse_args` 与缺参分支的文案原样搬入基类，不动；`Registry.execute` 宽 `except` 兜底不变（N4）。抽查命令验证缺参输出 `缺少必填参数: path`。
- **导入路径变更波及测试**：Part 1 改向 message/tool 的导入会触及 `tests/test_conversation.py:6`、`tests/test_agent.py:10`。缓解——仅改导入断言路径，测试断言不动；全量 `pytest` 验证路径全通。
- **`tool/__init__.py` 两 Part 共改**：Part 1 落地 `ToolDefinition` 本地定义建立边界，Part 2 再清内部 `BaseTool`/`_parse_args`，两 Part 互相独立但都改该文件——顺序上 Part 1 先行。
