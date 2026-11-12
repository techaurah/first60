"""The console channel (build step 5).

An interactive terminal channel: it reads one line at a time from
its input stream (``sys.stdin`` by default) and prints each reply
to its output stream (``sys.stdout`` by default). It is the channel
``first60 demo --interactive`` opens so a visitor can play the
customer themselves, and the channel a developer uses to talk to a
local engine without standing up the webhook server.

The input and output streams are injected so tests can drive the
channel with :class:`io.StringIO` instead of a real terminal. A
line that is empty after stripping is skipped, not sent to the
engine; end of input ends the session (``receive`` returns ``None``).
"""

from __future__ import annotations

import sys
from typing import TextIO

from first60.channels.base import InboundMessage

__all__ = [
    "ConsoleChannel",
]


class ConsoleChannel:
    """A terminal channel: stdin in, stdout out. Interactive use only."""

    name = "console"

    def __init__(
        self,
        input_stream: TextIO | None = None,
        output_stream: TextIO | None = None,
    ) -> None:
        self._input = input_stream or sys.stdin
        self._output = output_stream or sys.stdout

    def send(self, lead_id: str, text: str) -> None:
        """Print the reply (the lead id is not shown to the customer)."""
        print(text, file=self._output)
        self._output.flush()

    def receive(self) -> InboundMessage | None:
        """Read one line; blank lines are skipped, EOF ends the session."""
        while True:
            line = self._input.readline()
            if line == "":
                return None
            text = line.strip()
            if text:
                return InboundMessage(sender="console", text=text, channel="console")

    def run(self, handler) -> None:
        """Drive ``handler`` over the console until end of input.

        ``handler`` is called as ``handler(text) -> str | None`` for
        each line; a returned reply is printed. This is the loop the
        CLI's interactive demo uses; the engine owns the reply, the
        channel owns the terminal.
        """
        while True:
            message = self.receive()
            if message is None:
                return
            reply = handler(message.text)
            if reply:
                self.send(message.sender, reply)
