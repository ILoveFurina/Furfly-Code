"""进程内多轮对话历史。"""

from __future__ import annotations

from furflycode.message import (
    ROLE_ASSISTANT,
    ROLE_TOOL,
    ROLE_USER,
    Message,
    ToolCall,
    ToolResult,
)


class Conversation:
    """维护单次会话的对话历史（用户/助手/工具结果轮次）。

    历史仅保存在内存中，不写入磁盘。
    """

    def __init__(self) -> None:
        self._messages: list[Message] = []

    def add_user(self, text: str) -> None:
        """追加一条用户消息。"""
        self._messages.append(Message(role=ROLE_USER, content=text))

    def add_assistant(self, text: str) -> None:
        """追加一条助手消息。"""
        self._messages.append(Message(role=ROLE_ASSISTANT, content=text))

    def add_assistant_with_tool_calls(self, text: str, calls: list[ToolCall]) -> None:
        """追加一条带工具调用的助手回合。"""
        self._messages.append(
            Message(role=ROLE_ASSISTANT, content=text, tool_calls=list(calls))
        )

    def add_tool_results(self, results: list[ToolResult]) -> None:
        """追加一条工具结果回合（ROLE_TOOL）。"""
        self._messages.append(Message(role=ROLE_TOOL, tool_results=list(results)))

    def messages(self) -> list[Message]:
        """返回消息历史的浅拷贝。"""
        return list(self._messages)
