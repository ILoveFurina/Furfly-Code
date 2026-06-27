"""Anthropic 协议适配器 — 封装 AsyncAnthropic 以提供流式对话。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import anthropic

from furflycode.llm import Message, StreamEvent
from furflycode.prompt import SYSTEM_PROMPT

if TYPE_CHECKING:
    from furflycode.config import ProviderConfig


class AnthropicProvider:
    """由 Anthropic Messages API 提供支持的 LLM provider。"""

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        self._client = anthropic.AsyncAnthropic(
            api_key=config.api_key,
            base_url=config.base_url or None,
        )
        self._model = config.model
        self._thinking = config.thinking
    """
    @property 是 Python 的一个内置装饰器（decorator），它把方法变成 属性 来访问。
    对外的只读属性 name 和 model 只有 getter，外部无法直接赋值。
    """
    @property
    def name(self) -> str:
        return self._config.name

    @property
    def model(self) -> str:
        return self._config.model

    async def stream(self, msgs: list[Message]) -> AsyncIterator[StreamEvent]:
        """通过 Anthropic Messages API 流式发起一次对话轮次。

        思考增量会被静默丢弃。
        """
        api_msgs = [{"role": m.role, "content": m.content} for m in msgs]

        params: dict = {
            "model": self._model,
            "max_tokens": 4096,
            "system": SYSTEM_PROMPT,
            "messages": api_msgs,
        }

        if self._thinking:
            params["thinking"] = {
                "type": "enabled",
                "budget_tokens": 2048,
            }

        try:
            async with self._client.messages.stream(**params) as stream:
                async for event in stream:
                    if event.type == "content_block_delta":
                        delta = event.delta
                        # 跳过 thinking 增量
                        if delta.type == "thinking_delta":
                            continue
                        if delta.type == "text_delta":
                            yield StreamEvent(text=delta.text)
                    # 其他事件类型（message_start、content_block_start 等）
                    # 会被忽略 — 我们只关心文本增量。

            # 流正常完成（无异常地退出 `async with`）
            yield StreamEvent(done=True)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            yield StreamEvent(err=e)
