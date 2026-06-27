"""OpenAI 协议适配器 — 封装 AsyncOpenAI 以提供流式对话。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import openai

from furflycode.llm import Message, StreamEvent
from furflycode.prompt import SYSTEM_PROMPT

if TYPE_CHECKING:
    from furflycode.config import ProviderConfig


class OpenAIProvider:
    """由 OpenAI Chat Completions API 提供支持的 LLM provider。"""

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        self._client = openai.AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url or None,
        )
        self._model = config.model
        # OpenAI 会忽略 thinking 字段

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def model(self) -> str:
        return self._config.model

    async def stream(self, msgs: list[Message]) -> AsyncIterator[StreamEvent]:
        """通过 OpenAI Chat Completions API 流式发起一次对话轮次。"""
        api_msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + [
            {"role": m.role, "content": m.content} for m in msgs
        ]

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=api_msgs,
                stream=True,
            )

            async for chunk in response:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield StreamEvent(text=delta)

            yield StreamEvent(done=True)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            yield StreamEvent(err=e)
