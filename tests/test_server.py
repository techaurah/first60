"""Server tests (build step 5).

The stdlib HTTP server over the real engine: webhook round trip,
malformed payload rejection, the /status read surface, and the
demo chat page. The server binds an ephemeral localhost port; no
test touches the network beyond loopback.
"""

import json
import threading
import urllib.error
import urllib.request
from datetime import UTC, date, datetime

from first60.calendar.local import LocalCalendar
from first60.channels.simulated import SimulatedChannel
from first60.config import load_builtin_pack
from first60.engine import ReceptionEngine
from first60.pipeline.stages import Stage
from first60.respond.rules import RuleResponder
from first60.server import create_server, status_payload
from first60.store.memory import MemoryStore

PACK = load_builtin_pack("dental")
TUESDAY = datetime(2026, 11, 10, 21, 40, tzinfo=UTC)


def make_engine(write_mode="demo"):
    store = MemoryStore()
    channel = SimulatedChannel()
    calendar = LocalCalendar(store, PACK, clock=lambda: TUESDAY)
    engine = ReceptionEngine(
        pack=PACK,
        store=store,
        calendar=calendar,
        responder=RuleResponder(),
        channel=channel,
        clock=lambda: TUESDAY,
        write_mode=write_mode,
    )
    return engine, store


class _RunningServer:
    """A server on an ephemeral port, started and stopped per test."""

    def __init__(self, engine):
        self.server = create_server(engine, "127.0.0.1", 0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
        return False

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def post(self, path, payload, raw=False):
        body = payload if raw else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.url(path),
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def get(self, path):
        try:
            with urllib.request.urlopen(self.url(path)) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()


def test_webhook_round_trip_books_through_http():
    engine, store = make_engine()
    with _RunningServer(engine) as running:
        status, first = running.post(
            "/message",
            {
                "sender": "sarah",
                "text": "do you have anything Thursday morning, my crown is aching",
            },
        )
        assert status == 200
        assert "BrightSmile Dental" in first["reply"]
        running.post("/message", {"sender": "sarah", "text": "I'm Sarah"})
        running.post("/message", {"sender": "sarah", "text": "07123 456789"})
        status, fourth = running.post(
            "/message", {"sender": "sarah", "text": "Thursday 09:00 works for me"}
        )
        assert status == 200
        assert (
            "You're booked in for Crown fitting on Thursday 09:00." in fourth["reply"]
        )
    lead = store.list_leads()[0]
    assert lead.stage == Stage.BOOKED


def test_webhook_malformed_payloads_rejected():
    engine, _ = make_engine()
    with _RunningServer(engine) as running:
        status, body = running.post("/message", {"sender": "sarah"})
        assert status == 400
        assert body["error"] == "MALFORMED_PAYLOAD"
        status, body = running.post("/message", {"text": "hi"})
        assert status == 400
        assert body["error"] == "MALFORMED_PAYLOAD"
        status, body = running.post("/message", b"{not json", raw=True)
        assert status == 400
        assert body["error"] == "MALFORMED_PAYLOAD"
        status, body = running.post("/elsewhere", {"sender": "s", "text": "hi"})
        assert status == 404


def test_webhook_held_reply_answers_202():
    engine, _ = make_engine(write_mode="dry_run")
    with _RunningServer(engine) as running:
        status, body = running.post(
            "/message", {"sender": "sarah", "text": "do you have anything Thursday?"}
        )
        assert status == 202
        assert body["status"] == "held"


def test_status_surface_shape():
    engine, store = make_engine()
    with _RunningServer(engine) as running:
        status, raw = running.get("/status")
        assert status == 200
        payload = json.loads(raw)
        assert payload["business"] == "BrightSmile Dental"
        assert payload["leads_by_stage"]["NEW"] == 0
        assert payload["bookings_today"] == []
        assert payload["overdue"] == []
        assert payload["handed_off"] == []
        status, raw = running.get("/")
        assert status == 200
        assert b"First60 demo chat" in raw
        status, _ = running.get("/nope")
        assert status == 404


def test_status_payload_counts_bookings_and_overdue():
    engine, store = make_engine()
    engine.handle_inbound(
        "sarah", "do you have anything Thursday morning, my crown is aching"
    )
    engine.handle_inbound("sarah", "I'm Sarah")
    engine.handle_inbound("sarah", "07123 456789")
    engine.handle_inbound("sarah", "Thursday 09:00 works for me")
    payload = status_payload(engine, today=date(2026, 11, 12))
    assert payload["leads_by_stage"]["BOOKED"] == 1
    assert (
        payload["leads_by_band"].get("WARM") == 1
        or payload["leads_by_band"].get("HOT") == 1
    )
    assert len(payload["bookings_today"]) == 1
    assert payload["bookings_today"][0]["service"] == "Crown fitting"
    assert payload["overdue"] == []
