"""The HTTP server (build step 5).

A stdlib-only server (``http.server``) with three routes, all
served by one engine:

- ``POST /message``: the webhook channel. The body must be JSON
  ``{"sender": ..., "text": ...}``; a malformed body answers 400
  with ``{"error": "MALFORMED_PAYLOAD", ...}`` and never reaches
  the engine. A valid message is handled by the engine and the
  reply comes back as ``{"reply": ...}`` (200). When the engine
  withholds the reply (``dry_run`` / ``approval`` write mode) the
  answer is 202 ``{"status": "held", "reason": ...}``: nothing was
  sent, and the audit row says so.
- ``GET /status``: the daily-summary read surface. JSON with the
  business name, leads by stage and band, today's bookings, the
  overdue leads (contacted or qualified with no reply and no
  booking) and the handed-off leads. Read-only; it writes nothing.
- ``GET /``: a minimal demo chat page: a text box and a transcript
  that posts to ``/message``. It is a demo surface, not a product
  UI, and it sends through the same engine as the webhook.

The server binds ``127.0.0.1`` by default; binding a public
interface is the deployer's explicit choice at the CLI. It is
single-process and threaded, like the webhook channel it serves:
good enough for a receptionist's webhook, not a production
deployment claim.
"""

from __future__ import annotations

import json
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING

from first60.channels.webhook import parse_webhook_payload
from first60.engine import ReceptionEngine
from first60.errors import MALFORMED_PAYLOAD, First60Error
from first60.followups import local_now
from first60.pipeline.stages import Stage

if TYPE_CHECKING:
    from first60.store.base import Store

__all__ = [
    "create_server",
    "status_payload",
]

_DEMO_PAGE = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>First60 demo chat</title></head>
<body>
<h1>First60 demo chat</h1>
<p>Message the receptionist. This page talks to the same engine as
the webhook channel.</p>
<div id="log"></div>
<form id="form">
<input id="sender" placeholder="Your name or number" required>
<input id="text" placeholder="Type a message" required>
<button type="submit">Send</button>
</form>
<script>
const form = document.getElementById('form');
const log = document.getElementById('log');
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const sender = document.getElementById('sender').value;
  const text = document.getElementById('text').value;
  log.innerHTML += '<p><b>You:</b> ' + text + '</p>';
  const response = await fetch('/message', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({sender, text}),
  });
  const data = await response.json();
  const reply = data.reply || ('(' + (data.status || 'no reply') + ')');
  log.innerHTML += '<p><b>Receptionist:</b> ' + reply + '</p>';
});
</script>
</body>
</html>
"""


def status_payload(engine: ReceptionEngine, today: date | None = None) -> dict:
    """Build the ``/status`` read surface from the engine's store.

    ``today`` defaults to the business-local date at the engine's
    clock. Overdue means a lead in CONTACTED or QUALIFIED with no
    booking and no reply since the last outbound; handed-off means
    automation is paused for the lead.
    """
    store: Store = engine.store
    day = today or local_now(engine.pack, engine.clock()).date()
    by_stage: dict[str, int] = {stage.value: 0 for stage in Stage}
    by_band: dict[str, int] = {}
    overdue: list[dict[str, str]] = []
    handed_off: list[dict[str, str]] = []
    for lead in store.list_leads():
        by_stage[lead.stage.value] += 1
        by_band[lead.score_band] = by_band.get(lead.score_band, 0) + 1
        state = lead.state or {}
        if state.get("automation_paused") is True:
            handed_off.append(
                {"id": lead.id, "name": lead.name, "stage": lead.stage.value}
            )
        elif lead.stage in (Stage.CONTACTED, Stage.QUALIFIED):
            overdue.append(
                {"id": lead.id, "name": lead.name, "stage": lead.stage.value}
            )
    bookings = [
        {
            "id": appointment.id,
            "lead_id": appointment.lead_id,
            "service": appointment.service,
            "start": appointment.start,
        }
        for appointment in store.list_appointments(day)
        if appointment.status == "booked"
    ]
    return {
        "business": engine.pack.name,
        "date": day.isoformat(),
        "leads_by_stage": by_stage,
        "leads_by_band": by_band,
        "bookings_today": bookings,
        "overdue": overdue,
        "handed_off": handed_off,
    }


def _handler_class(engine: ReceptionEngine) -> type[BaseHTTPRequestHandler]:
    """Build the request handler bound to ``engine``."""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # noqa: D102 - keep test output clean
            pass

        def do_GET(self):  # noqa: N802
            if self.path == "/status":
                self._send_json(200, status_payload(engine))
            elif self.path == "/":
                payload = _DEMO_PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            else:
                self._send_json(404, {"error": "NOT_FOUND"})

        def do_POST(self):  # noqa: N802
            if self.path != "/message":
                self._send_json(404, {"error": "NOT_FOUND"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b""
            try:
                data = json.loads(raw.decode("utf-8")) if raw else None
                sender, text = parse_webhook_payload(data)
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._send_json(
                    400,
                    {
                        "error": MALFORMED_PAYLOAD,
                        "detail": "webhook body must be valid JSON",
                    },
                )
                return
            except First60Error as exc:
                self._send_json(400, {"error": exc.code, "detail": exc.detail})
                return
            reply = engine.handle_inbound(sender, text, channel_name="webhook")
            if reply is None:
                self._send_json(
                    202,
                    {
                        "status": "held",
                        "reason": (
                            "no automated reply: lead paused/opted out, "
                            "or the write mode withheld the send"
                        ),
                    },
                )
                return
            self._send_json(200, {"reply": reply})

        def _send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def create_server(
    engine: ReceptionEngine,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> ThreadingHTTPServer:
    """Create (but do not start) the webhook server for ``engine``."""
    return ThreadingHTTPServer((host, port), _handler_class(engine))
