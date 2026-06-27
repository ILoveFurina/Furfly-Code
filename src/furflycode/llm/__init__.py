"""LLM 协议层 — 与 provider 无关的类型与工厂。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Literal, Protocol, runtime_checkable

from furflycode.config import ProviderConfig


@dataclass
class Message:
    """单条聊天消息。"""

    role: Literal["user", "assistant"]
    content: str


@dataclass
class StreamEvent:
    """provider 流式生成器产出的一条事件。"""

    text: str = ""  # 文本增量
    done: bool = False  # 当前轮次正常结束
    err: Exception | None = None  # 错误（与 done 互斥）


@runtime_checkable
class Provider(Protocol):
    """与协议无关的 LLM provider 接口。"""

    @property
    def name(self) -> str:
        """状态栏左侧显示的名称。"""
        ...

    @property
    def model(self) -> str:
        """状态栏右侧显示的模型名。"""
        ...

    def stream(self, msgs: list[Message]) -> AsyncIterator[StreamEvent]:
        """发起一次流式对话轮次。

        实现应当：
        - 注入内置的系统提示。
        - 在适用时启用 thinking 配置。
        - 为每个文本增量产出 StreamEvent(text=...)。
        - 丢弃 thinking 增量（不产出）。
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


__all__ = ["Message", "StreamEvent", "Provider", "new_provider"]
