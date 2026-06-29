"""Tests for the conversation module."""

from __future__ import annotations

from furflycode.conversation import Conversation
from furflycode.llm import ToolCall, ToolResult


def test_empty_conversation():
    """A fresh conversation has no messages."""
    conv = Conversation()
    assert conv.messages() == []


def test_add_user_and_assistant_order():
    """Messages are stored in insertion order with correct roles."""
    conv = Conversation()
    conv.add_user("hello")
    conv.add_assistant("hi there")
    conv.add_user("how are you")
    conv.add_assistant("fine")

    msgs = conv.messages()
    assert len(msgs) == 4
    roles = [m.role for m in msgs]
    assert roles == ["user", "assistant", "user", "assistant"]
    assert msgs[0].content == "hello"
    assert msgs[3].content == "fine"


def test_messages_returns_copy():
    """messages() returns a copy; mutating it doesn't affect internal state."""
    conv = Conversation()
    conv.add_user("hello")
    snapshot = conv.messages()
    snapshot.clear()
    # Internal state unaffected
    assert len(conv.messages()) == 1


def test_tool_turns_appended():
    """工具调用回合与工具结果回合按序追加且内容正确。"""
    conv = Conversation()
    conv.add_user("read it")
    conv.add_assistant_with_tool_calls(
        "let me check", [ToolCall(id="t1", name="read_file", input='{"path":"a"}')]
    )
    conv.add_tool_results(
        [ToolResult(tool_call_id="t1", content="file contents", is_error=False)]
    )
    conv.add_assistant("done")

    msgs = conv.messages()
    assert len(msgs) == 4
    roles = [m.role for m in msgs]
    assert roles == ["user", "assistant", "tool", "assistant"]
    assert msgs[1].tool_calls[0].name == "read_file"
    assert msgs[1].tool_calls[0].input == '{"path":"a"}'
    assert msgs[2].tool_results[0].tool_call_id == "t1"
    assert msgs[2].tool_results[0].content == "file contents"
    assert msgs[3].content == "done"
