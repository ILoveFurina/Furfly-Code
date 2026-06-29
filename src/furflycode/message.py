"""协议无关的消息与工具调用传输词汇。

这些类型跨越 agent / tool / conversation / llm 各层，本身不绑定任何 LLM 协议；
各 provider 在边界处把它们转换成自家 API 的形状。本模块仅依赖标准库，是工程内的
中性叶子模块，任何层都可依赖它而不引入方向倒置。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

# 消息角色字面量。
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_TOOL = "tool"  # 携带工具执行结果的回合


@dataclass
class ToolCall:
    """协议无关地承载模型发起的一次工具调用（流式拼接完成后）。

    属性：
        id: provider 侧调用 id；回灌结果时配对。
        name: 工具名（注册中心按名查找）。
        input: 拼接完成的 JSON 参数字符串（raw JSON）。
    """

    id: str
    name: str
    input: str


@dataclass
class ToolResult:
    """协议无关地承载一次工具执行结果。

    属性：
        tool_call_id: 对应 ToolCall.id。
        content: 执行产出（成功内容或结构化错误文本）。
        is_error: 是否为错误结果（F9）。
    """

    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass
class Message:
    """单条聊天消息。

    assistant 回合可携带 tool_calls；ROLE_TOOL 回合携带 tool_results。
    """

    role: Literal["user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)  # 仅 assistant
    tool_results: list[ToolResult] = field(default_factory=list)  # 仅 ROLE_TOOL


@dataclass
class StreamEvent:
    """provider 流式生成器产出的一条事件。

    四态语义：
        text: 文本增量（preamble 或最终答复）。
        tool_calls: 非空表示本轮模型请求执行这些工具（在 done 之前发出）。
        done: 当前轮次正常结束。
        err: 错误（与 done 互斥）。
    """

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    done: bool = False
    err: Exception | None = None


def dumps_tool_input(obj: Any) -> str:
    """把工具参数对象序列化为 JSON 字符串（供 ToolCall.input 使用）。"""
    return json.dumps(obj, ensure_ascii=False)


__all__ = [
    "Message",
    "StreamEvent",
    "ToolCall",
    "ToolResult",
    "ROLE_USER",
    "ROLE_ASSISTANT",
    "ROLE_TOOL",
    "dumps_tool_input",
]
