"""The demo scenario (build step 6).

DESIGN.md section 9: ``python -m first60 demo`` loads the dental
pack as fictional BrightSmile Dental, seeds the local calendar with
busy blocks, sets the simulated clock to Tuesday 21:40, and runs a
scripted scenario through the real engine against the simulated
channel and clock. The scenario is not a recording: the same
:func:`run_demo` the CLI runs is the release-gate integration test
(``tests/test_demo.py``), so a visitor and the test suite see the
same transcript.

The demo week is fixed (Tuesday 2026-11-10 to Wednesday 2026-11-11)
so the transcript is reproducible. Europe/London is on GMT in
November, so business-local and UTC agree throughout; the times are
still formatted through the pack timezone, not assumed.

The scenario, in clock order:

- Tuesday 12:00: Priya enquires about teeth whitening on Wednesday
  morning, answers the questions, is offered Wednesday slots, and
  goes quiet.
- Tuesday 16:00: follow-up touch 1 fires (+4h) and Priya books
  Wednesday 09:00 from it.
- Tuesday 21:47: Sarah's after-hours enquiry ("do you have anything
  Thursday morning, my crown is aching") is qualified in three
  questions, offered real free slots, and booked for Thursday 09:00.
  The seeded busy block (an existing patient, Thursday 10:30) is
  visible in the offer: the 60-minute crown cannot start at 10:00,
  so the offer reads 09:00, 09:30, 11:00. The score is printed with
  its components.
- Still 21:47: Sarah messages again; dedupe holds (one lead, one
  appointment) and she hears an acknowledgement naming her booking.
- Tuesday 22:05: Sam enquires, then replies STOP; the audit shows
  the opt-out and no further touches are scheduled for him.
- Wednesday 08:00: the daily summary prints (leads by stage and
  band, the booking list, overdue and handed-off leads).

``python -m first60 demo --interactive`` instead opens the console
channel on a fresh copy of the same seeded world, so a visitor can
play the customer themselves. The engine's channel stays the
simulated outbox in that mode: the console loop prints each reply
exactly once, and the engine never sends anywhere real.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from first60.calendar.local import LocalCalendar
from first60.channels.console import ConsoleChannel
from first60.channels.simulated import SimulatedChannel
from first60.config import BusinessPack, load_builtin_pack
from first60.engine import ReceptionEngine
from first60.followups import local_now
from first60.models import Lead, new_appointment, new_lead
from first60.pipeline.stages import Stage
from first60.respond.rules import RuleResponder
from first60.server import status_payload
from first60.store.base import Store
from first60.store.memory import MemoryStore

__all__ = [
    "DemoResult",
    "SimulatedClock",
    "build_demo_world",
    "render_daily_summary",
    "run_demo",
    "run_interactive",
    "seed_demo_calendar",
]

# The demo week. Tuesday 2026-11-10, Wednesday 2026-11-11, Thursday
# 2026-11-12; Europe/London is on GMT in November.
TUESDAY = date(2026, 11, 10)
WEDNESDAY = date(2026, 11, 11)
THURSDAY = date(2026, 11, 12)
_NOON = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
_TOUCH_TIME = datetime(2026, 11, 10, 16, 0, tzinfo=UTC)
_AFTER_HOURS = datetime(2026, 11, 10, 21, 47, tzinfo=UTC)
_OPT_OUT_TIME = datetime(2026, 11, 10, 22, 5, tzinfo=UTC)
_SUMMARY_TIME = datetime(2026, 11, 11, 8, 0, tzinfo=UTC)

# One seeded busy block: an existing patient holds Thursday 10:30
# for a 30-minute check-up, so the 60-minute crown offer skips
# 10:00 and 10:30.
_SEEDED_DAY = THURSDAY
_SEEDED_START = "2026-11-12T10:30:00"
_SEEDED_SERVICE = "Check-up and clean"
_SEEDED_DURATION = 30

# Score components, in the order the summary prints them.
_SCORE_COMPONENTS = (
    "service_fit",
    "urgency",
    "contact",
    "completeness",
    "value",
    "engagement",
)


class SimulatedClock:
    """A clock the demo sets by hand; :meth:`now` returns the set time."""

    def __init__(self, start: datetime) -> None:
        self._now = start

    def now(self) -> datetime:
        """Return the time the demo last set."""
        return self._now

    def set(self, moment: datetime) -> None:
        """Move the clock to ``moment`` (never backwards in the demo)."""
        self._now = moment


@dataclass
class DemoResult:
    """Everything the scripted demo produced, for the CLI and tests."""

    engine: ReceptionEngine
    store: Store
    clock: SimulatedClock
    transcript: list[str] = field(default_factory=list)
    summary: str = ""


def _display_name(lead: Lead) -> str:
    """Return the lead's name, or a short id when none was captured."""
    name = (lead.answers or {}).get("name") or lead.name
    return name or f"lead {lead.id[:8]}"


def _format_local(pack: BusinessPack, moment: datetime) -> str:
    """Format an aware UTC time as business-local ``Weekday HH:MM``."""
    return local_now(pack, moment).strftime("%A %H:%M")


def seed_demo_calendar(store: Store) -> Lead:
    """Seed one busy block: an existing patient, Thursday 10:30.

    Busy blocks are booked appointments in this design, so the seed
    is a real lead in stage BOOKED with a real appointment. It is
    narrated up front in the demo, and it shows in the summary's
    booking list as the pre-existing booking it is. The seeded lead
    never consented to reminders and never heard from the engine,
    so it gets no follow-ups and no reminders.
    """
    lead = store.create_lead(
        new_lead(name="Existing patient", channel="seed", now=_NOON.isoformat())
    )
    for target in (Stage.CONTACTED, Stage.QUALIFIED, Stage.BOOKED):
        lead = store.move_stage(lead.id, target)
    store.save_appointment(
        new_appointment(
            lead_id=lead.id,
            service=_SEEDED_SERVICE,
            start=_SEEDED_START,
            duration_minutes=_SEEDED_DURATION,
            idempotency_key="seed-thursday-1030",
        )
    )
    return lead


def build_demo_world(
    channel: SimulatedChannel,
) -> tuple[ReceptionEngine, Store, SimulatedClock]:
    """Build the demo engine: dental pack, memory store, seeded calendar.

    The clock starts at Tuesday 21:40 (DESIGN.md section 9); the
    scripted acts set it explicitly as the scenario moves through
    the day, so the noon enquiry and its 16:00 follow-up run at
    their real times.
    """
    pack = load_builtin_pack("dental")
    store = MemoryStore()
    clock = SimulatedClock(_AFTER_HOURS.replace(hour=21, minute=40))
    calendar = LocalCalendar(store, pack, clock=clock.now)
    engine = ReceptionEngine(
        pack=pack,
        store=store,
        calendar=calendar,
        responder=RuleResponder(),
        channel=channel,
        clock=clock.now,
        write_mode="demo",
    )
    seed_demo_calendar(store)
    return engine, store, clock


def render_daily_summary(engine: ReceptionEngine, day: date | None = None) -> str:
    """Render the daily pipeline summary as plain text.

    The stage and band counts come from the server's ``/status``
    surface (:func:`first60.server.status_payload`), so the printed
    summary and the HTTP surface can never disagree; the booking
    list covers every booked appointment (not just today's), and
    paused leads are split into handed-off and opted-out, which the
    status payload lumps together.
    """
    store = engine.store
    payload = status_payload(engine, today=day)
    summary_date = date.fromisoformat(payload["date"])
    lines = [
        "Daily summary — "
        f"{payload['business']} — {summary_date.strftime('%A %Y-%m-%d')}",
        "Leads by stage: "
        + ", ".join(
            f"{stage.value}: {payload['leads_by_stage'][stage.value]}"
            for stage in Stage
        ),
        "Leads by band: "
        + ", ".join(
            f"{band}: {payload['leads_by_band'].get(band, 0)}"
            for band in ("HOT", "WARM", "NURTURE", "LOW")
        ),
        "Bookings:",
    ]
    booked = [item for item in store.list_appointments() if item.status == "booked"]
    if not booked:
        lines.append("  none")
    for item in booked:
        start = datetime.fromisoformat(item.start)
        lead = store.get_lead(item.lead_id)
        lines.append(
            f"  {start.strftime('%A %H:%M')} — {item.service} — {_display_name(lead)}"
        )
    overdue = [
        _display_name(lead)
        for lead in store.list_leads()
        if lead.stage in (Stage.CONTACTED, Stage.QUALIFIED)
        and not (lead.state or {}).get("automation_paused")
    ]
    handed_off = [
        _display_name(lead)
        for lead in store.list_leads()
        if (lead.state or {}).get("automation_paused")
        and not (lead.state or {}).get("opted_out")
    ]
    opted_out = [
        _display_name(lead)
        for lead in store.list_leads()
        if (lead.state or {}).get("opted_out")
    ]
    lines.append(f"Overdue: {', '.join(overdue) if overdue else 'none'}")
    lines.append(f"Handed off: {', '.join(handed_off) if handed_off else 'none'}")
    lines.append(f"Opted out: {', '.join(opted_out) if opted_out else 'none'}")
    return "\n".join(lines)


def _lead_by_name(store: Store, name: str) -> Lead:
    """Return the lead whose captured name is ``name``."""
    return next(lead for lead in store.list_leads() if lead.answers.get("name") == name)


def run_demo(print_fn=print) -> DemoResult:
    """Run the scripted demo scenario; return everything it produced.

    ``print_fn`` receives every printed line (``print`` by default),
    so the CLI shows the transcript and the release-gate test can
    capture the identical script.
    """
    channel = SimulatedChannel()
    engine, store, clock = build_demo_world(channel)
    pack = engine.pack
    transcript: list[str] = []

    def emit(line: str = "") -> None:
        transcript.append(line)
        print_fn(line)

    def say(sender: str, text: str) -> None:
        emit(f"[{_format_local(pack, clock.now())}] {sender}: {text}")

    def inbound(sender: str, text: str) -> str | None:
        say(sender, text)
        reply = engine.handle_inbound(sender, text)
        if reply is not None:
            say(pack.name, reply)
        return reply

    emit("First60 demo — BrightSmile Dental (fictional).")
    emit("No keys, no network, no accounts: the real engine, a")
    emit("simulated channel, and a clock you can watch move.")
    emit("")
    emit("The calendar already holds one booking: an existing")
    emit("patient, Thursday 10:30. Watch the 10:00 slot disappear")
    emit("from the crown offers below — availability is real.")
    emit("")
    emit("--- Tuesday 12:00 — a noon enquiry goes quiet ---")
    clock.set(_NOON)
    inbound("priya", "Hi, I'd like teeth whitening on Wednesday morning")
    inbound("priya", "I'm Priya")
    inbound("priya", "priya@example.com")
    emit("Priya goes quiet with Wednesday slots on the table.")
    emit("")
    emit("--- Tuesday 16:00 — follow-up touch 1 fires (+4h) ---")
    clock.set(_TOUCH_TIME)
    for text in engine.process_due():
        say(pack.name, text)
    inbound("priya", "Wednesday 09:00 works for me")
    priya = _lead_by_name(store, "Priya")
    emit(
        f"Priya booked from the follow-up: {priya.service} "
        f"Wednesday 09:00, stage {priya.stage.value}."
    )
    emit("")
    emit("--- Tuesday 21:47 — the after-hours enquiry ---")
    clock.set(_AFTER_HOURS)
    inbound("sarah", "do you have anything Thursday morning, my crown is aching")
    inbound("sarah", "I'm Sarah")
    inbound("sarah", "07123 456789")
    inbound("sarah", "Thursday 09:00 works for me")
    sarah = _lead_by_name(store, "Sarah")
    components = ", ".join(
        f"{name} {sarah.score_components.get(name, 0)}" for name in _SCORE_COMPONENTS
    )
    emit(
        f"Sarah: stage NEW -> {sarah.stage.value}, score "
        f"{sarah.score_total} ({sarah.score_band}) — {components}."
    )
    emit("One enquiry, one reply inside the first minute, one booking.")
    emit("")
    emit("--- Still 21:47 — the same lead messages again ---")
    demo_leads = [lead for lead in store.list_leads() if lead.channel != "seed"]
    before = len(demo_leads)
    reply = inbound("sarah", "Thanks! See you Thursday")
    assert reply is not None
    after = len([lead for lead in store.list_leads() if lead.channel != "seed"])
    emit(
        f"Dedupe holds: {before} demo leads before, {after} after — "
        "no duplicate lead, no second appointment."
    )
    emit("")
    emit("--- Tuesday 22:05 — an opt-out ---")
    clock.set(_OPT_OUT_TIME)
    inbound("sam", "Hi, I'm Sam. Do you do whitening?")
    inbound("sam", "STOP")
    sam = _lead_by_name(store, "Sam")
    scheduled = store.list_followups(lead_id=sam.id, status="scheduled")
    emit(
        f"Sam opted out: audit shows opt_out, {len(scheduled)} "
        "further touches scheduled. He hears nothing more."
    )
    emit("")
    emit("--- Wednesday 08:00 — the daily summary ---")
    clock.set(_SUMMARY_TIME)
    summary = render_daily_summary(engine, day=WEDNESDAY)
    for line in summary.splitlines():
        emit(line)
    return DemoResult(
        engine=engine,
        store=store,
        clock=clock,
        transcript=transcript,
        summary=summary,
    )


def run_interactive(
    engine: ReceptionEngine | None = None,
    console: ConsoleChannel | None = None,
    print_fn=print,
) -> int:
    """Open the console channel so a visitor can play the customer.

    A fresh seeded world is built when no engine is given. The
    visitor is one lead on the console channel, on the simulated
    Tuesday 21:40 clock, so Thursday slots are bookable exactly as
    in the scripted demo. End the session with Ctrl-D (EOF).
    """
    if engine is None:
        engine, _, _ = build_demo_world(SimulatedChannel())
    if console is None:
        console = ConsoleChannel()
    print_fn("First60 demo — interactive mode.")
    print_fn(
        f"You are the customer, messaging {engine.pack.name} on "
        "Tuesday 21:40. Answer the questions, then pick a slot "
        'like "Thursday 09:00" to book it.'
    )
    print_fn("Type Ctrl-D to stop.")
    print_fn("")
    console.run(lambda text: engine.handle_inbound("console", text))
    print_fn("")
    print_fn("Session ended. The demo business is fictional; nothing")
    print_fn("was sent anywhere and no booking is real.")
    return 0
