"""The simulated channel (build step 5).

A scripted channel for the demo and for tests. It is constructed
with a list of ``(sender, text)`` pairs; :meth:`SimulatedChannel.receive`
pops the next pair and :meth:`SimulatedChannel.send` appends the
outbound text to :attr:`SimulatedChannel.outbox` instead of sending
it anywhere. Nothing here touches the network, a clock, or a real
person, which is exactly why the demo scenario (build step 6) and
the integration test can run the real engine against it and assert
on the exact transcript.

The outbox records ``(lead_id, text)`` pairs in send order, so a
test can assert both what was sent and the order it was sent in.
"""

from __future__ import annotations

from first60.channels.base import InboundMessage

__all__ = [
    "SimulatedChannel",
]


class SimulatedChannel:
    """A scripted inbound queue with a fake outbox. Demo and tests only."""

    name = "simulated"

    def __init__(self, script: list[tuple[str, str]] | None = None) -> None:
        self._script: list[tuple[str, str]] = list(script or [])
        self.outbox: list[tuple[str, str]] = []

    def queue(self, sender: str, text: str) -> None:
        """Append one scripted inbound message to the end of the script."""
        self._script.append((sender, text))

    def has_more(self) -> bool:
        """Return True while scripted inbound messages remain."""
        return bool(self._script)

    def send(self, lead_id: str, text: str) -> None:
        """Record the outbound text in the outbox; send nothing anywhere."""
        self.outbox.append((lead_id, text))

    def receive(self) -> InboundMessage | None:
        """Pop the next scripted message, or None when the script is done."""
        if not self._script:
            return None
        sender, text = self._script.pop(0)
        return InboundMessage(sender=sender, text=text, channel="simulated")
