"""Scaffold a starter business pack (build step 7).

``first60 init`` copies one of the shipped builtin packs to a
user-editable location, so a new business starts from a working
pack instead of a blank file. The copy is plain text: the owner
edits services, questions, hours and emergency terms in their own
editor, then runs it with ``first60 serve --pack-file <path>``.

Everything here is deterministic and offline: no network, no
templates fetched from anywhere, no prompts. The written file is
validated with the same strict loader that serves it, so a bad
scaffold can never be handed to the user as done.
"""

from __future__ import annotations

import re
from pathlib import Path

from first60.config import PACKS_DIR, VERTICALS, PackError, load_builtin_pack, load_pack

__all__ = [
    "next_steps",
    "scaffold_pack",
]

# The [business] section header, and the name line inside it.
_BUSINESS_SECTION_RE = re.compile(r"^\[business\]\s*$", re.MULTILINE)
_NAME_LINE_RE = re.compile(r"^(\s*name\s*=\s*)\"[^\"]*\"\s*$", re.MULTILINE)

DEFAULT_OUTPUT = Path("my-business.toml")


def _replace_business_name(text: str, business_name: str) -> str:
    """Replace the ``name`` line inside the [business] section only.

    Only the first ``name = "..."`` line after ``[business]`` is
    touched, so a service or question that happens to carry a name
    is never rewritten by accident.
    """
    section = _BUSINESS_SECTION_RE.search(text)
    if section is None:
        raise PackError("business.name", "builtin pack has no [business] section")
    head, rest = text[: section.end()], text[section.end() :]
    match = _NAME_LINE_RE.search(rest)
    if match is None:
        raise PackError("business.name", "builtin pack has no business name line")
    # Stop at the next section header: the name must be inside
    # [business], not in a later table.
    next_section = re.search(r"^\[", rest, re.MULTILINE)
    if next_section is not None and match.start() > next_section.start():
        raise PackError("business.name", "builtin pack has no business name line")
    new_rest = (
        rest[: match.start()]
        + f'{match.group(1)}"{business_name}"'
        + rest[match.end() :]
    )
    return head + new_rest


def scaffold_pack(
    pack_name: str = "dental",
    business_name: str | None = None,
    output: str | Path = DEFAULT_OUTPUT,
    force: bool = False,
) -> Path:
    """Copy a builtin pack to ``output`` and validate the copy.

    ``pack_name`` is one of the shipped verticals (``"dental"`` by
    default). ``business_name`` replaces the pack's business name
    when given. An existing ``output`` is left untouched unless
    ``force`` is set. Returns the written path. Raises
    :class:`PackError` for an unknown pack, a bad business name, an
    existing output, or a copy that fails validation.
    """
    if pack_name not in VERTICALS:
        raise PackError(
            "pack", f"unknown builtin pack {pack_name!r}: use one of {VERTICALS}"
        )
    if business_name is not None:
        business_name = business_name.strip()
        if not business_name or '"' in business_name or "\n" in business_name:
            raise PackError(
                "business.name",
                "must be a non-empty name without quotes or line breaks",
            )
    # Validate the source pack first: a broken builtin must fail
    # here, not after a file has been written.
    load_builtin_pack(pack_name)
    source = PACKS_DIR / f"{pack_name}.toml"
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise PackError("pack", f"cannot read builtin pack {source}: {exc}") from exc
    if business_name is not None:
        text = _replace_business_name(text, business_name)
    out_path = Path(output)
    if out_path.exists() and not force:
        raise PackError(
            "pack",
            f"{out_path} already exists; pass --force to overwrite it",
        )
    if out_path.parent != Path("."):
        out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    # Validate what was written, with the same loader serve uses.
    load_pack(out_path)
    return out_path


def next_steps(output: Path, pack_name: str) -> str:
    """The next steps printed after a successful ``first60 init``."""
    return "\n".join(
        [
            f"Created {output} from the {pack_name} pack.",
            "Next steps:",
            f"  1. Edit {output}: set your business name, services, "
            "questions, hours and emergency terms.",
            f"  2. Run it: first60 serve --pack-file {output}",
            "  3. Read docs/configuration.md for every pack field.",
        ]
    )
