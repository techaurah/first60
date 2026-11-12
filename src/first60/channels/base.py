"""The channel protocol (build step 5).

One protocol for every text channel First60 talks on: the generic
JSON webhook channel (the integration surface for forms and future
platform adapters), the console channel (interactive demo and
debugging), and the simulated channel (scripted demo and tests).

The protocol is deliberately small. A channel delivers outbound
text with :meth:`Channel.send` and yields the next inbound message
with :meth:`Channel.receive`:

- The simulated channel pops the next scripted message and returns
  ``None`` when the script is exhausted.
- The console channel reads one line from its input stream and
  returns ``None`` on end of input.
- The webhook channel is push-driven: the HTTP server hands inbound
  messages to the engine directly, so its ``receive`` returns
  ``None`` and its ``send`` records the reply in an outbox the
  server reads back as the HTTP response.

A channel never decides anything: it carries text. Extraction,
scoring, stage moves and follow-up timing live in the pipeline and
the engine (build step 5), and every send the engine makes is
audited there. The ``lead_id`` a channel send takes is the store
id of the lead the text goes to; the channel does not resolve
senders to leads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

__all__ = [
    "Channel",
    "InboundMessage",
]


@dataclass(frozen=True)
class InboundMessage:
    """One inbound message, as a channel received it.

    ``sender`` is the channel handle that identifies the person
    (a phone number, an email, a webhook sender id, or a console
    name); the engine uses it to dedupe the lead. ``channel`` names
    the transport (``"simulated"``, ``"console"``, ``"webhook"``).
    ``received_at`` is the UTC time the message arrived, or ``None``
    when the channel does not timestamp (the simulated channel in
    tests, which runs on the injected clock instead).
    """

    sender: str
    text: str
    channel: str
    received_at: datetime | None = None


class Channel(Protocol):
    """Sends outbound text and yields inbound messages, one at a time."""

    name: str

    def send(self, lead_id: str, text: str) -> None:
        """Deliver ``text`` to ``lead_id`` on this channel."""
        ...

    def receive(self) -> InboundMessage | None:
        """Return the next inbound message, or ``None`` when there is none."""
        ...
