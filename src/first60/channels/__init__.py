"""Channel package (build step 5).

One protocol, three transports: the generic JSON webhook channel,
the interactive console channel, and the scripted simulated
channel for demo and tests.
"""

from first60.channels.base import Channel, InboundMessage
from first60.channels.console import ConsoleChannel
from first60.channels.simulated import SimulatedChannel
from first60.channels.webhook import WebhookChannel, parse_webhook_payload

__all__ = [
    "Channel",
    "ConsoleChannel",
    "InboundMessage",
    "SimulatedChannel",
    "WebhookChannel",
    "parse_webhook_payload",
]
