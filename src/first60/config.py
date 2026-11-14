"""Business pack loading and validation.

A business pack is one TOML file in ``packs/`` describing a single
service business: its services, qualifying questions, hours, follow-up
policy, handoff rules and booking terms. Loading uses only stdlib
``tomllib``; a pack that fails validation raises :class:`PackError`
naming the broken field, so a bad pack can never silently load.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "BusinessPack",
    "FollowUpPolicy",
    "HandoffRules",
    "PackError",
    "QualifyingQuestion",
    "Service",
    "WEEKDAYS",
    "_find_packs_dir",
    "load_builtin_pack",
    "load_pack",
]

WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

VERTICALS = ("dental", "plumber", "med-spa", "clinic", "real-estate")

VALUE_TIERS = ("low", "standard", "high")

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


# Repo root is two levels above this file (src/first60/config.py).
# An installed wheel carries packs/ inside the package instead
# (site-packages/first60/packs); see _find_packs_dir.
def _find_packs_dir(package_dir: Path | None = None) -> Path:
    """Locate the directory holding the shipped business packs.

    An installed copy wins when present: the wheel ships ``packs/``
    inside the package, so an installed First60 can load a builtin
    pack. Otherwise fall back to the repo layout (``packs/`` at the
    repo root, two levels above this file). ``package_dir`` exists
    for tests to stand in for an installed package directory.
    """
    base = package_dir or Path(__file__).resolve().parent
    in_package = base / "packs"
    if in_package.is_dir():
        return in_package
    return Path(__file__).resolve().parents[2] / "packs"


PACKS_DIR = _find_packs_dir()


class PackError(ValueError):
    """A business pack failed to load or validate.

    ``field`` names the broken field (for example ``"services"`` or
    ``"hours.monday.open"``); ``reason`` explains what is wrong.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        self.field = field_name
        self.reason = reason
        super().__init__(f"pack field {field_name!r}: {reason}")


@dataclass(frozen=True)
class Service:
    """One bookable service offered by the business."""

    name: str
    duration_minutes: int
    value_tier: str
    description: str = ""


@dataclass(frozen=True)
class QualifyingQuestion:
    """One question the receptionist asks while qualifying a lead."""

    id: str
    text: str
    required: bool = True


@dataclass(frozen=True)
class FollowUpPolicy:
    """When follow-up touches fire, and the waking window they obey."""

    touch_delays_hours: tuple[int, ...] = (4, 24, 72)
    max_touches: int = 3
    waking_window_start: str = "08:00"
    waking_window_end: str = "21:00"


@dataclass(frozen=True)
class HandoffRules:
    """When the receptionist hands a lead to the human owner."""

    emergency_terms: tuple[str, ...] = ()
    emergency_instruction: str = ""
    handoff_only: tuple[str, ...] = ()


@dataclass(frozen=True)
class BusinessPack:
    """A validated business pack, ready for the receptionist engine."""

    name: str
    vertical: str
    timezone: str
    currency: str
    services: tuple[Service, ...]
    questions: tuple[QualifyingQuestion, ...]
    hours: dict[str, tuple[str, str] | None]
    followups: FollowUpPolicy
    handoff: HandoffRules
    slot_minutes: int = 30
    confirmation_required: bool = True

    def service_names(self) -> list[str]:
        """Return the bookable service names in pack order."""
        return [service.name for service in self.services]


def _require_mapping(data: object, field_name: str) -> dict[str, object]:
    if not isinstance(data, dict):
        raise PackError(field_name, "must be a table")
    return data


def _require_string(data: dict[str, object], key: str, field_name: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PackError(field_name, "must be a non-empty string")
    return value.strip()


def _require_bool(data: dict[str, object], key: str, field_name: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise PackError(field_name, "must be true or false")
    return value


def _validate_time(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _TIME_RE.match(value):
        raise PackError(field_name, "must be a 24-hour time like '09:00'")
    return value


def _validate_hours(data: object) -> dict[str, tuple[str, str] | None]:
    hours = _require_mapping(data, "hours")
    parsed: dict[str, tuple[str, str] | None] = {}
    for day in WEEKDAYS:
        day_data = hours.get(day)
        if day_data is None:
            raise PackError(f"hours.{day}", "every weekday must be present")
        day_table = _require_mapping(day_data, f"hours.{day}")
        if day_table.get("closed") is True:
            parsed[day] = None
            continue
        open_time = _validate_time(day_table.get("open"), f"hours.{day}.open")
        close_time = _validate_time(day_table.get("close"), f"hours.{day}.close")
        if open_time >= close_time:
            raise PackError(
                f"hours.{day}",
                f"open time {open_time} must be before close time {close_time}",
            )
        parsed[day] = (open_time, close_time)
    return parsed


def _validate_services(data: object) -> tuple[Service, ...]:
    if not isinstance(data, list) or not data:
        raise PackError("services", "must be a non-empty list")
    services: list[Service] = []
    seen: set[str] = set()
    for index, raw in enumerate(data):
        base = f"services[{index}]"
        table = _require_mapping(raw, base)
        name = _require_string(table, "name", f"{base}.name")
        if name.lower() in seen:
            raise PackError(f"{base}.name", f"duplicate service name {name!r}")
        seen.add(name.lower())
        duration = table.get("duration_minutes")
        if (
            not isinstance(duration, int)
            or isinstance(duration, bool)
            or duration < 5
            or duration > 480
        ):
            raise PackError(
                f"{base}.duration_minutes",
                "must be a whole number of minutes between 5 and 480",
            )
        tier = table.get("value_tier")
        if tier not in VALUE_TIERS:
            raise PackError(
                f"{base}.value_tier",
                f"must be one of {', '.join(VALUE_TIERS)}",
            )
        description = table.get("description", "")
        if not isinstance(description, str):
            raise PackError(f"{base}.description", "must be a string")
        services.append(
            Service(
                name=name,
                duration_minutes=duration,
                value_tier=str(tier),
                description=description,
            )
        )
    return tuple(services)


def _validate_questions(data: object) -> tuple[QualifyingQuestion, ...]:
    if not isinstance(data, list) or not data:
        raise PackError("questions", "must be a non-empty list")
    questions: list[QualifyingQuestion] = []
    seen: set[str] = set()
    for index, raw in enumerate(data):
        base = f"questions[{index}]"
        table = _require_mapping(raw, base)
        question_id = _require_string(table, "id", f"{base}.id")
        if question_id in seen:
            raise PackError(f"{base}.id", f"duplicate question id {question_id!r}")
        seen.add(question_id)
        text = _require_string(table, "text", f"{base}.text")
        required = table.get("required", True)
        if not isinstance(required, bool):
            raise PackError(f"{base}.required", "must be true or false")
        questions.append(
            QualifyingQuestion(id=question_id, text=text, required=required)
        )
    return tuple(questions)


def _validate_followups(data: object) -> FollowUpPolicy:
    table = _require_mapping(data, "followups")
    delays = table.get("touch_delays_hours")
    if (
        not isinstance(delays, list)
        or not delays
        or any(
            not isinstance(delay, int) or isinstance(delay, bool) or delay <= 0
            for delay in delays
        )
        or list(delays) != sorted(delays)
    ):
        raise PackError(
            "followups.touch_delays_hours",
            "must be a non-empty list of increasing positive whole hours",
        )
    max_touches = table.get("max_touches")
    if (
        not isinstance(max_touches, int)
        or isinstance(max_touches, bool)
        or max_touches < 1
        or max_touches > len(delays)
    ):
        raise PackError(
            "followups.max_touches",
            "must be a whole number between 1 and the number of touch delays",
        )
    start = _validate_time(
        table.get("waking_window_start"), "followups.waking_window_start"
    )
    end = _validate_time(table.get("waking_window_end"), "followups.waking_window_end")
    if start >= end:
        raise PackError(
            "followups.waking_window_start",
            f"waking window start {start} must be before end {end}",
        )
    return FollowUpPolicy(
        touch_delays_hours=tuple(delays),
        max_touches=max_touches,
        waking_window_start=start,
        waking_window_end=end,
    )


def _validate_handoff(data: object) -> HandoffRules:
    table = _require_mapping(data, "handoff")
    terms = table.get("emergency_terms")
    if (
        not isinstance(terms, list)
        or not terms
        or any(not isinstance(term, str) or not term.strip() for term in terms)
    ):
        raise PackError(
            "handoff.emergency_terms",
            "must be a non-empty list of non-empty strings",
        )
    instruction = _require_string(
        table, "emergency_instruction", "handoff.emergency_instruction"
    )
    only = table.get("handoff_only", [])
    if not isinstance(only, list) or any(
        not isinstance(item, str) or not item.strip() for item in only
    ):
        raise PackError("handoff.handoff_only", "must be a list of non-empty strings")
    return HandoffRules(
        emergency_terms=tuple(term.strip() for term in terms),
        emergency_instruction=instruction,
        handoff_only=tuple(item.strip() for item in only),
    )


def _validate_booking(data: object) -> tuple[int, bool]:
    table = _require_mapping(data, "booking")
    slot_minutes = table.get("slot_minutes", 30)
    if (
        not isinstance(slot_minutes, int)
        or isinstance(slot_minutes, bool)
        or slot_minutes < 5
        or slot_minutes > 480
    ):
        raise PackError(
            "booking.slot_minutes",
            "must be a whole number of minutes between 5 and 480",
        )
    confirmation = (
        _require_bool(table, "confirmation_required", "booking.confirmation_required")
        if "confirmation_required" in table
        else True
    )
    return slot_minutes, confirmation


def load_pack(path: str | Path) -> BusinessPack:
    """Load and validate a business pack from a TOML file.

    Raises :class:`PackError` naming the broken field when the file is
    missing, is not valid TOML, or fails validation.
    """
    pack_path = Path(path)
    try:
        raw = pack_path.read_bytes()
    except OSError as exc:
        raise PackError("pack", f"cannot read pack file {pack_path}: {exc}") from exc
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise PackError("pack", f"invalid TOML: {exc}") from exc

    business = _require_mapping(data.get("business"), "business")
    name = _require_string(business, "name", "business.name")
    vertical = _require_string(business, "vertical", "business.vertical")
    if vertical not in VERTICALS:
        raise PackError("business.vertical", f"must be one of {', '.join(VERTICALS)}")
    timezone = _require_string(business, "timezone", "business.timezone")
    currency = _require_string(business, "currency", "business.currency")
    if len(currency) != 3 or not currency.isalpha():
        raise PackError(
            "business.currency", "must be a 3-letter currency code like 'GBP'"
        )

    services = _validate_services(data.get("services"))
    questions = _validate_questions(data.get("questions"))
    hours = _validate_hours(data.get("hours"))
    followups = _validate_followups(data.get("followups"))
    handoff = _validate_handoff(data.get("handoff"))
    slot_minutes, confirmation_required = _validate_booking(data.get("booking"))

    return BusinessPack(
        name=name,
        vertical=vertical,
        timezone=timezone,
        currency=currency.upper(),
        services=services,
        questions=questions,
        hours=hours,
        followups=followups,
        handoff=handoff,
        slot_minutes=slot_minutes,
        confirmation_required=confirmation_required,
    )


def load_builtin_pack(name: str) -> BusinessPack:
    """Load one of the packs shipped in ``packs/`` by file stem.

    For example ``load_builtin_pack("dental")`` loads ``packs/dental.toml``.
    """
    if not name or "/" in name or "\\" in name:
        raise PackError("pack", f"invalid pack name {name!r}")
    return load_pack(PACKS_DIR / f"{name}.toml")


def builtin_pack_names() -> list[str]:
    """Return the stems of the packs shipped in ``packs/``, sorted."""
    if not PACKS_DIR.is_dir():
        return []
    return sorted(path.stem for path in PACKS_DIR.glob("*.toml"))
