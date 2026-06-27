"""进程内多轮对话历史。"""

from __future__ import annotations

from furflycode.llm import Message


class Conversation:
    """维护单次会话的对话历史（用户/助手轮次）。

    历史仅保存在内存中，不写入磁盘。
    """

    def __init__(self) -> None:
        self._messages: list[Message] = []

    def add_user(self, text: str) -> None:
        """追加一条用户消息。"""
        self._messages.append(Message(role="user", content=text))

    def add_assistant(self, text: str) -> None:
        """追加一条助手消息。"""
        self._messages.append(Message(role="assistant", content=text))

    def messages(self) -> list[Message]:
        """返回消息历史的浅拷贝。"""
        return list(self._messages)
