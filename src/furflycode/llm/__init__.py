"""LLM 协议层 — Provider 契约与工厂。

协议无关的消息/工具调用传输类型见 ``furflycode.message``；工具定义见
``furflycode.tool.ToolDefinition``。本模块只保留与具体 LLM 协议绑定的
Provider 适配器契约与工厂，不再充当全工程的共享词汇库。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from furflycode.config import ProviderConfig
from furflycode.message import Message, StreamEvent
from furflycode.tool import ToolDefinition


@runtime_checkable
class Provider(Protocol):
    """
    适配器目标接口 Target
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


__all__ = ["Provider", "new_provider"]
