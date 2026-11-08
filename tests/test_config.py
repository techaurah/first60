"""Tests for business pack loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from first60.config import (
    PACKS_DIR,
    PackError,
    load_builtin_pack,
    load_pack,
)

PACK_NAMES = ["dental", "plumber", "med-spa", "clinic", "real-estate"]

EXPECTED_NAMES = {
    "dental": "BrightSmile Dental",
    "plumber": "SwiftFlow Plumbing",
    "med-spa": "GlowHaven Med Spa",
    "clinic": "Harborview Family Clinic",
    "real-estate": "Keystone Homes Realty",
}


@pytest.mark.parametrize("name", PACK_NAMES)
def test_all_five_packs_load_and_validate(name: str) -> None:
    """Every shipped pack loads through the real config loader."""
    pack = load_pack(PACKS_DIR / f"{name}.toml")
    assert pack.name == EXPECTED_NAMES[name]
    assert pack.vertical in {"dental", "plumber", "med-spa", "clinic", "real-estate"}
    assert len(pack.services) >= 3
    assert len(pack.questions) >= 3
    assert len(pack.hours) == 7
    assert pack.handoff.emergency_terms
    assert pack.handoff.emergency_instruction


@pytest.mark.parametrize("name", PACK_NAMES)
def test_all_five_packs_share_follow_up_defaults(name: str) -> None:
    """Every pack uses the design defaults: +4h, +24h, +72h, max 3 touches."""
    pack = load_pack(PACKS_DIR / f"{name}.toml")
    assert pack.followups.touch_delays_hours == (4, 24, 72)
    assert pack.followups.max_touches == 3
    assert pack.followups.waking_window_start == "08:00"
    assert pack.followups.waking_window_end == "21:00"


@pytest.mark.parametrize("name", PACK_NAMES)
def test_all_five_packs_have_sunday_closed(name: str) -> None:
    """Every shipped pack closes on Sunday (hours are real, not filler)."""
    pack = load_pack(PACKS_DIR / f"{name}.toml")
    assert pack.hours["sunday"] is None
    assert pack.hours["monday"] is not None
    assert pack.service_names() == [service.name for service in pack.services]


def test_load_builtin_pack_by_name() -> None:
    """The builtin loader finds packs by stem, as the demo will use it."""
    pack = load_builtin_pack("dental")
    assert pack.name == "BrightSmile Dental"
    assert pack.vertical == "dental"


def test_load_builtin_pack_rejects_bad_name() -> None:
    """Path tricks in a pack name are rejected with a named error."""
    with pytest.raises(PackError) as excinfo:
        load_builtin_pack("../dental")
    assert excinfo.value.field == "pack"


def test_missing_pack_file_raises_named_field_error(tmp_path: Path) -> None:
    """A missing pack file fails with a named field, not a bare OSError."""
    with pytest.raises(PackError) as excinfo:
        load_pack(tmp_path / "no-such-pack.toml")
    assert excinfo.value.field == "pack"


def test_malformed_toml_raises_named_field_error(tmp_path: Path) -> None:
    """Broken TOML fails with a named field."""
    bad = tmp_path / "bad.toml"
    bad.write_text("[business\nname = 'broken'\n", encoding="utf-8")
    with pytest.raises(PackError) as excinfo:
        load_pack(bad)
    assert excinfo.value.field == "pack"


def _write_pack(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "pack.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _valid_pack_text() -> str:
    return (PACKS_DIR / "dental.toml").read_text(encoding="utf-8")


def test_broken_pack_no_services_section(tmp_path: Path) -> None:
    """A pack missing the services table fails on the services field."""
    kept: list[str] = []
    in_services = False
    for line in _valid_pack_text().splitlines():
        if line.startswith("[[services]]"):
            in_services = True
            continue
        if line.startswith("[[questions]]"):
            in_services = False
        if not in_services:
            kept.append(line)
    path = _write_pack(tmp_path, "\n".join(kept))
    with pytest.raises(PackError) as excinfo:
        load_pack(path)
    assert excinfo.value.field == "services"


def test_broken_pack_bad_value_tier(tmp_path: Path) -> None:
    """An unknown value tier fails naming the value_tier field."""
    text = _valid_pack_text().replace(
        'value_tier = "standard"', 'value_tier = "gold"', 1
    )
    path = _write_pack(tmp_path, text)
    with pytest.raises(PackError) as excinfo:
        load_pack(path)
    assert excinfo.value.field == "services[0].value_tier"


def test_broken_pack_bad_opening_time(tmp_path: Path) -> None:
    """An opening time that is not a 24-hour time fails on the hours field."""
    text = _valid_pack_text().replace('"09:00"', '"9am"', 1)
    path = _write_pack(tmp_path, text)
    with pytest.raises(PackError) as excinfo:
        load_pack(path)
    assert excinfo.value.field.startswith("hours.")


def test_broken_pack_empty_emergency_terms(tmp_path: Path) -> None:
    """A pack with no emergency terms fails on the handoff field."""
    text = _valid_pack_text().replace(
        'emergency_terms = ["severe pain", "swelling", "bleeding", '
        '"knocked out tooth", "face swelling"]',
        "emergency_terms = []",
    )
    path = _write_pack(tmp_path, text)
    with pytest.raises(PackError) as excinfo:
        load_pack(path)
    assert excinfo.value.field == "handoff.emergency_terms"


def test_broken_pack_bad_follow_up_delays(tmp_path: Path) -> None:
    """Follow-up delays that do not increase fail on the followups field."""
    text = _valid_pack_text().replace(
        "touch_delays_hours = [4, 24, 72]", "touch_delays_hours = [24, 4, 72]"
    )
    path = _write_pack(tmp_path, text)
    with pytest.raises(PackError) as excinfo:
        load_pack(path)
    assert excinfo.value.field == "followups.touch_delays_hours"
