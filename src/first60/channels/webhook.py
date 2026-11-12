"""The generic JSON webhook channel (build step 5).

The integration surface for forms and future platform adapters:
an HTTP POST carrying JSON ``{"sender": ..., "text": ...}`` becomes
one inbound message, and the reply goes back as the HTTP response
body (see :mod:`first60.server`). The channel itself is deliberately
thin: it validates the payload shape and records outbound text in
an outbox the server reads. It opens no socket of its own; the
server owns the socket.

Payload rules, enforced by :func:`parse_webhook_payload`:

- The body must be a JSON object with string ``sender`` and
  ``text`` fields, both non-empty after stripping.
- Anything else is a malformed payload: the caller gets a
  :class:`first60.errors.First60Error` with code
  ``MALFORMED_PAYLOAD`` and a detail naming the broken field, and
  the server answers 400. A malformed payload never reaches the
  engine, so a bad form post can never create a lead or a reply.

The channel is push-driven, so :meth:`WebhookChannel.receive`
always returns ``None``: inbound messages arrive through the
server, not by polling the channel.
"""

from __future__ import annotations

from first60.channels.base import InboundMessage
from first60.errors import MALFORMED_PAYLOAD, First60Error

__all__ = [
    "WebhookChannel",
    "parse_webhook_payload",
]


def parse_webhook_payload(data: object) -> tuple[str, str]:
    """Validate a decoded JSON webhook body; return ``(sender, text)``.

    Raises :class:`first60.errors.First60Error` with code
    ``MALFORMED_PAYLOAD`` when the body is not an object or when
    ``sender`` or ``text`` is missing, not a string, or blank.
    """
    if not isinstance(data, dict):
        raise First60Error(MALFORMED_PAYLOAD, "webhook body must be a JSON object")
    sender = data.get("sender")
    if not isinstance(sender, str) or not sender.strip():
        raise First60Error(
            MALFORMED_PAYLOAD, "webhook field 'sender' must be a non-empty string"
        )
    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        raise First60Error(
            MALFORMED_PAYLOAD, "webhook field 'text' must be a non-empty string"
        )
    return sender.strip(), text.strip()


class WebhookChannel:
    """A JSON webhook channel. Push-driven; the server owns the socket."""

    name = "webhook"

    def __init__(self) -> None:
        self.outbox: dict[str, list[str]] = {}

    def send(self, lead_id: str, text: str) -> None:
        """Record the reply; the server returns it as the HTTP response."""
        self.outbox.setdefault(lead_id, []).append(text)

    def receive(self) -> InboundMessage | None:
        """Push-driven channels are never polled; always None."""
        return None
