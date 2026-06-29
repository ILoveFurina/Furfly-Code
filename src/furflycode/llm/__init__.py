"""LLM 协议层 — 与 provider 无关的类型与工厂。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal, Protocol, runtime_checkable

from furflycode.config import ProviderConfig

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
class ToolDefinition:
    """注册中心导出的协议无关工具定义。

    属性：
        name: 工具名。
        description: 给模型的用途说明。
        input_schema: 完整 JSON Schema（type/properties/required）。
    """

    name: str
    description: str
    input_schema: dict[str, Any]


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


@runtime_checkable
class Provider(Protocol):
    """
    适配器目标接口 Target

    提供统一的Provider结构给被适配者(agent层)
    通过Protocol(静态鸭子类型)，只要它的属性和方法与 Provider 形状一致，
    类型检查器（mypy/pyright）就会把它视为 Provider 的合法实现。这种行为叫结构化子类型
    """

    @property
    def name(self) -> str:
        """状态栏左侧显示的名称。"""
        ...

    @property
    def model(self) -> str:
        """状态栏右侧显示的模型名。"""
        ...

    def stream(
        self,
        msgs: list[Message],
        tools: list[ToolDefinition],
    ) -> AsyncIterator[StreamEvent]:
        """发起一次流式对话轮次。

        实现应当：
        - 注入内置的系统提示。
        - 在适用时启用 thinking 配置（含工具历史的请求需关闭）。
        - 注入 tools 定义（空列表表示不带工具）。
        - 为每个文本增量产出 StreamEvent(text=...)。
        - 丢弃 thinking 增量（不产出）。
        - 本轮模型请求工具时，在 done 之前产出 StreamEvent(tool_calls=...)。
        - 正常完成时产出 StreamEvent(done=True)。
        - 出错时产出 StreamEvent(err=...)。
        """
        ...


def new_provider(config: ProviderConfig) -> Provider:
    """根据 *config* 中的协议创建 Provider 适配器。

    参数：
        config: provider 配置。

    返回：
        对应协议的适配器实例。

    抛出：
        ValueError: 未知协议时抛出。
    """
    if config.protocol == "anthropic":
        from furflycode.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(config)
    elif config.protocol == "openai":
        from furflycode.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(config)
    else:
        raise ValueError(f"未知协议: {config.protocol!r}")


def dumps_tool_input(obj: Any) -> str:
    """把工具参数对象序列化为 JSON 字符串（供 ToolCall.input 使用）。"""
    return json.dumps(obj, ensure_ascii=False)


__all__ = [
    "Message",
    "StreamEvent",
    "Provider",
    "new_provider",
    "ToolCall",
    "ToolResult",
    "ToolDefinition",
    "ROLE_USER",
    "ROLE_ASSISTANT",
    "ROLE_TOOL",
    "dumps_tool_input",
]
