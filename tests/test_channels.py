"""Channel tests (build step 5).

One protocol, three transports: the simulated channel (scripted
demo/tests), the console channel (interactive terminal) and the
webhook channel (JSON in, reply out). A channel carries text; it
never decides anything.
"""

import io

import pytest

from first60.channels.base import InboundMessage
from first60.channels.console import ConsoleChannel
from first60.channels.simulated import SimulatedChannel
from first60.channels.webhook import WebhookChannel, parse_webhook_payload
from first60.errors import MALFORMED_PAYLOAD, First60Error


def test_simulated_channel_plays_script_in_order():
    channel = SimulatedChannel([("sarah", "hello"), ("omar", "do you have Thursday?")])
    assert channel.has_more()
    first = channel.receive()
    assert first == InboundMessage(sender="sarah", text="hello", channel="simulated")
    second = channel.receive()
    assert second is not None and second.sender == "omar"
    assert channel.receive() is None
    assert not channel.has_more()


def test_simulated_channel_outbox_records_sends_in_order():
    channel = SimulatedChannel()
    channel.queue("sarah", "hi")
    assert channel.receive() is not None
    channel.send("lead-1", "Hello Sarah")
    channel.send("lead-1", "What is your name?")
    assert channel.outbox == [
        ("lead-1", "Hello Sarah"),
        ("lead-1", "What is your name?"),
    ]


def test_console_channel_reads_lines_and_skips_blanks():
    stream = io.StringIO("hello\n\nworld\n")
    channel = ConsoleChannel(input_stream=stream, output_stream=io.StringIO())
    first = channel.receive()
    assert first is not None and first.text == "hello"
    assert first.channel == "console"
    second = channel.receive()
    assert second is not None and second.text == "world"
    assert channel.receive() is None


def test_console_channel_send_prints_and_run_drives_handler():
    output = io.StringIO()
    channel = ConsoleChannel(
        input_stream=io.StringIO("hi\nbye\n"), output_stream=output
    )
    channel.run(lambda text: f"echo: {text}")
    assert output.getvalue() == "echo: hi\necho: bye\n"


def test_webhook_payload_valid():
    assert parse_webhook_payload({"sender": "sarah", "text": " hello "}) == (
        "sarah",
        "hello",
    )


@pytest.mark.parametrize(
    "body",
    [
        None,
        "not an object",
        ["sender", "text"],
        {},
        {"sender": "sarah"},
        {"text": "hi"},
        {"sender": "", "text": "hi"},
        {"sender": "sarah", "text": "   "},
        {"sender": 42, "text": "hi"},
        {"sender": "sarah", "text": None},
    ],
)
def test_webhook_payload_malformed(body):
    with pytest.raises(First60Error) as excinfo:
        parse_webhook_payload(body)
    assert excinfo.value.code == MALFORMED_PAYLOAD


def test_webhook_channel_records_outbox_and_never_polls():
    channel = WebhookChannel()
    assert channel.receive() is None
    channel.send("lead-1", "Hello Sarah")
    assert channel.outbox == {"lead-1": ["Hello Sarah"]}


def test_channels_share_the_protocol():
    for channel in (SimulatedChannel(), ConsoleChannel(), WebhookChannel()):
        assert isinstance(channel.name, str) and channel.name
        assert callable(channel.send)
        assert callable(channel.receive)
