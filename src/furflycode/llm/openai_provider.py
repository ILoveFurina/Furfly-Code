"""OpenAI 协议适配器 — 封装 AsyncOpenAI 以提供流式对话与工具调用。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import openai

from furflycode.llm import (
    ROLE_ASSISTANT,
    ROLE_TOOL,
    Message,
    StreamEvent,
    ToolCall,
    ToolDefinition,
)
from furflycode.prompt import SYSTEM_PROMPT

if TYPE_CHECKING:
    from furflycode.config import ProviderConfig


def _to_openai_tools(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    """把协议无关 ToolDefinition 列表转为 OpenAI tools 参数。"""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
            },
        }
        for t in tools
    ]


def _to_openai_messages(msgs: list[Message]) -> list[dict[str, Any]]:
    """把协议无关 Message 列表转为 OpenAI messages 参数。

    assistant 工具调用回合发 tool_calls 数组；ROLE_TOOL 回合每个 ToolResult 发一条
    role=tool 消息。
    """
    api_msgs: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in msgs:
        if m.role == ROLE_TOOL and m.tool_results:
            for r in m.tool_results:
                api_msgs.append(
                    {
                        "role": "tool",
                        "tool_call_id": r.tool_call_id,
                        "content": r.content,
                    }
                )
        elif m.role == ROLE_ASSISTANT and m.tool_calls:
            api_msgs.append(
                {
                    "role": ROLE_ASSISTANT,
                    "content": m.content or None,
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {
                                "name": c.name,
                                "arguments": c.input or "{}",
                            },
                        }
                        for c in m.tool_calls
                    ],
                }
            )
        else:
            api_msgs.append({"role": m.role, "content": m.content})
    return api_msgs


class OpenAIProvider:
    """由 OpenAI Chat Completions API 提供支持的 LLM provider。"""

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        self._client = openai.AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url or None,
        )
        self._model = config.model

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def model(self) -> str:
        return self._config.model

    async def stream(
        self,
        msgs: list[Message],
        tools: list[ToolDefinition],
    ) -> AsyncIterator[StreamEvent]:
        """通过 OpenAI Chat Completions API 流式发起一次对话轮次。"""
        api_msgs = _to_openai_messages(msgs)
        params: dict[str, Any] = {
            "model": self._model,
            "messages": api_msgs,
            "stream": True,
        }
        if tools:
            params["tools"] = _to_openai_tools(tools)

        # 按 index 累加分片工具调用（多工具下同时分片）。
        tool_calls_buf: dict[int, dict[str, str]] = {}

        try:
            response = await self._client.chat.completions.create(**params)
            async for chunk in response:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                if delta and delta.content:
                    yield StreamEvent(text=delta.content)
                if delta and delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index if tc.index is not None else 0
                        slot = tool_calls_buf.setdefault(idx, {"id": "", "name": ""})
                        if tc.id:
                            slot["id"] = tc.id
                        if tc.function and tc.function.name:
                            slot["name"] = tc.function.name
                        if tc.function and tc.function.arguments:
                            slot["args"] = slot.get("args", "") + tc.function.arguments

            if tool_calls_buf:
                calls = [
                    ToolCall(
                        id=tool_calls_buf[i]["id"],
                        name=tool_calls_buf[i]["name"],
                        input=tool_calls_buf[i].get("args") or "{}",
                    )
                    for i in sorted(tool_calls_buf)
                ]
                if calls:
                    yield StreamEvent(tool_calls=calls)

            yield StreamEvent(done=True)

        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — 错误包成事件回灌
            yield StreamEvent(err=e)
