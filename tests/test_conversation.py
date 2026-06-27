"""Tests for the conversation module."""

from __future__ import annotations

from furflycode.conversation import Conversation


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
