"""Anthropic 协议适配器 — 封装 AsyncAnthropic 以提供流式对话与工具调用。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import anthropic
from anthropic.types import ToolUseBlock

from furflycode.message import (
    ROLE_ASSISTANT,
    ROLE_TOOL,
    ROLE_USER,
    Message,
    StreamEvent,
    ToolCall,
    Usage,
    dumps_tool_input,
)
from furflycode.prompt import SYSTEM_PROMPT
from furflycode.tool import ToolDefinition

if TYPE_CHECKING:
    from furflycode.config import ProviderConfig


def _to_anthropic_tools(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    """把协议无关 ToolDefinition 列表转为 Anthropic tools 参数。"""
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_schema,
        }
        for t in tools
    ]


def _has_tool_history(msgs: list[Message]) -> bool:
    """判断消息历史是否含工具交互回合（用于关闭 thinking，避免 400）。"""
    for m in msgs:
        if m.role == ROLE_TOOL and m.tool_results:
            return True
        if m.role == ROLE_ASSISTANT and m.tool_calls:
            return True
    return False


def _to_anthropic_messages(msgs: list[Message]) -> list[dict[str, Any]]:
    """把协议无关 Message 列表转为 Anthropic messages 参数。

    assistant 工具调用回合 content 用 [text, tool_use...] 数组；
    ROLE_TOOL 回合把每个 ToolResult 拼进一条 user 消息的 content 数组。
    """
    api_msgs: list[dict[str, Any]] = []
    for m in msgs:
        if m.role == ROLE_TOOL and m.tool_results:
            # 工具结果回合映射为一条 user 消息，content 为 tool_result 块数组。
            content: list[dict[str, Any]] = [
                {
                    "type": "tool_result",
                    "tool_use_id": r.tool_call_id,
                    "content": r.content,
                    "is_error": r.is_error,
                }
                for r in m.tool_results
            ]
            api_msgs.append({"role": ROLE_USER, "content": content})
        elif m.role == ROLE_ASSISTANT and m.tool_calls:
            content = []
            if m.content:
                content.append({"type": "text", "text": m.content})
            for c in m.tool_calls:
                try:
                    input_obj = json.loads(c.input) if c.input else {}
                except json.JSONDecodeError:
                    input_obj = {}
                content.append(
                    {
                        "type": "tool_use",
                        "id": c.id,
                        "name": c.name,
                        "input": input_obj,
                    }
                )
            api_msgs.append({"role": ROLE_ASSISTANT, "content": content})
        else:
            api_msgs.append({"role": m.role, "content": m.content})
    return api_msgs


class AnthropicProvider:
    """
    Anthropic 适配器 具体一点就是 Anthropic stream适配器
    通过上面三个工具类 将Anthropic原生stream 适配为了本项目通用的stream
    用项目通用的Events,Tool,Message 传入此适配器 屏蔽了Anthropic API
    """

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        self._client = anthropic.AsyncAnthropic(
            api_key=config.api_key,
            base_url=config.base_url or None,
        )
        self._model = config.model
        self._thinking = config.thinking

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
        """
        通过 Anthropic Messages API 流式发起一次对话轮次。
        思考增量会被静默丢弃；工具调用在流结束后一次性上抛。
        """
        api_msgs = _to_anthropic_messages(msgs)

        params: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 4096,
            "system": SYSTEM_PROMPT,
            "messages": api_msgs,
        }
        if tools:
            params["tools"] = _to_anthropic_tools(tools)
        # 含工具历史的请求关闭 thinking（避免签名缺失导致 400）。
        if self._thinking and not _has_tool_history(msgs):
            params["thinking"] = {
                "type": "enabled",
                "budget_tokens": 2048,
            }

        try:
            async with self._client.messages.stream(**params) as stream:
                async for event in stream:
                    if event.type == "content_block_delta":
                        delta = event.delta
                        # 跳过 thinking 增量与工具参数分片
                        # SDK 内部累加器保留完整 input
                        if delta.type in ("thinking_delta", "input_json_delta"):
                            continue
                        if delta.type == "text_delta":
                            yield StreamEvent(text=delta.text)
                # 区别于OpenAI只能代码累加，Anthropic的SDK上下文管理自带累加器
                # Anthropic提供了一个get_final_message()取得最终完整的message对象
                final_message = await stream.get_final_message()
                if final_message.stop_reason == "tool_use":
                    calls: list[ToolCall] = []
                    for block in final_message.content:
                        if isinstance(block, ToolUseBlock):
                            calls.append(
                                ToolCall(
                                    id=block.id,
                                    name=block.name,
                                    input=dumps_tool_input(block.input),
                                )
                            )
                    if calls:
                        yield StreamEvent(tool_calls=calls)
                # token 用量回传（尽力而为；usage 始终在 final_message 上）
                u = final_message.usage
                cache_read = getattr(u, "cache_read_input_tokens", None)
                cache_create = getattr(u, "cache_creation_input_tokens", None)
                yield StreamEvent(
                    usage=Usage(
                        input_tokens=u.input_tokens,
                        output_tokens=u.output_tokens,
                        cache_read_tokens=cache_read,
                        cache_creation_tokens=cache_create,
                    )
                )

            yield StreamEvent(done=True)

        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — 错误包成事件回灌
            yield StreamEvent(err=e)
