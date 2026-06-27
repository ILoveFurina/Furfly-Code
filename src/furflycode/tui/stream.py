"""Stream consumption and timing logic for the TUI.

These functions are called from furflycodeApp with the app instance
as their first argument.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from rich.text import Text

from furflycode.tui.view import assistant_block, error_block, streaming_text

if TYPE_CHECKING:
    from furflycode.tui.app import furflycodeApp


async def consume_stream(app: furflycodeApp) -> None:
    """Consume the provider stream, updating the UI in real-time.

    Launched as an asyncio.Task from the App.
    """
    try:
        async for ev in app.provider.stream(app.conv.messages()):
            if ev.err is not None:
                await _finish_with_error(app, ev.err)
                return
            if ev.text:
                app.cur_reply += ev.text
                _refresh_streaming_view(app)
            if ev.done:
                await _finish_with_assistant(app, app.cur_reply)
                return
    except asyncio.CancelledError:
        raise
    except Exception as e:
        await _finish_with_error(app, e)


def tick(app: furflycodeApp) -> None:
    """Timer callback — refresh the streaming indicator every ~100 ms."""
    from furflycode.tui.app import SessionState

    if app.state != SessionState.STREAMING:
        return
    elapsed = time.monotonic() - app.turn_start
    streaming_widget = app.query_one("#streaming")
    streaming_widget.update(streaming_text(app.cur_reply, elapsed))


def _refresh_streaming_view(app: furflycodeApp) -> None:
    """Update the streaming area with the current reply buffer and timer."""
    elapsed = time.monotonic() - app.turn_start
    streaming_widget = app.query_one("#streaming")
    streaming_widget.update(streaming_text(app.cur_reply, elapsed))


async def _finish_with_assistant(app: furflycodeApp, reply: str) -> None:
    """Finalize a successful assistant turn."""
    from furflycode.tui.app import SessionState

    log = app.query_one("#log")
    # Render final reply as markdown
    log.write(assistant_block(reply))
    # Persist to conversation history
    app.conv.add_assistant(reply)
    # Show elapsed time
    elapsed = time.monotonic() - app.turn_start
    log.write(Text(f"  ({elapsed:.1f}s)", style="dim"))
    # Clean up
    _stop_streaming(app)
    app.state = SessionState.IDLE
    app.query_one("#input").focus()


async def _finish_with_error(app: furflycodeApp, err: Exception) -> None:
    """Finalize a failed turn: display error, reset state."""
    from furflycode.tui.app import SessionState

    log = app.query_one("#log")
    log.write(error_block(err))
    _stop_streaming(app)
    app.state = SessionState.IDLE
    app.query_one("#input").focus()


def _stop_streaming(app: furflycodeApp) -> None:
    """Stop the streaming timer and clear the streaming area."""
    if app._timer is not None:
        app._timer.stop()
        app._timer = None
    app._stream_task = None
    app.cur_reply = ""
    streaming_widget = app.query_one("#streaming")
    streaming_widget.update("")
