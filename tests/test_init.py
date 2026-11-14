"""Tests for ``first60 init`` (build step 7) and the installed pack layout.

``init`` scaffolds a starter business pack from a builtin pack: a
plain TOML copy the owner edits, then runs with
``first60 serve --pack-file <path>``. Everything is offline and
deterministic; the tests run in a temp directory and never touch
the repo's own packs/.
"""

from __future__ import annotations

import shutil

import pytest

from first60 import cli
from first60.config import PACKS_DIR, _find_packs_dir, load_pack


def test_init_copies_dental_pack(tmp_path, monkeypatch, capsys) -> None:
    """``first60 init`` writes a valid copy of the dental pack."""
    monkeypatch.chdir(tmp_path)
    assert cli.main(["init"]) == 0
    out = capsys.readouterr().out
    assert "Created my-business.toml from the dental pack." in out
    assert "first60 serve --pack-file my-business.toml" in out

    written = tmp_path / "my-business.toml"
    assert written.exists()
    assert written.read_text(encoding="utf-8") == (
        (PACKS_DIR / "dental.toml").read_text(encoding="utf-8")
    )
    pack = load_pack(written)
    assert pack.name == "BrightSmile Dental"
    assert pack.vertical == "dental"
    assert len(pack.services) == 5


def test_init_with_name_replaces_business_name_only(tmp_path, monkeypatch) -> None:
    """``--name`` renames the business, and nothing else changes."""
    monkeypatch.chdir(tmp_path)
    assert cli.main(["init", "--name", "Acme Dental"]) == 0
    pack = load_pack(tmp_path / "my-business.toml")
    assert pack.name == "Acme Dental"
    assert pack.vertical == "dental"
    assert pack.service_names() == load_pack(PACKS_DIR / "dental.toml").service_names()
    # No other "name" line in the file was rewritten: the pack still
    # has its five services and five questions.
    assert len(pack.services) == 5
    assert len(pack.questions) == 5


@pytest.mark.parametrize("pack_name", ["plumber", "med-spa", "clinic", "real-estate"])
def test_init_each_builtin_pack(tmp_path, monkeypatch, pack_name: str) -> None:
    """Every builtin vertical scaffolds to a valid pack."""
    monkeypatch.chdir(tmp_path)
    output = tmp_path / f"{pack_name}.toml"
    assert cli.main(["init", "--pack", pack_name, "--output", str(output)]) == 0
    assert load_pack(output).vertical == pack_name


def test_init_refuses_overwrite_without_force(tmp_path, monkeypatch, capsys) -> None:
    """A second init without --force fails and leaves the file alone."""
    monkeypatch.chdir(tmp_path)
    assert cli.main(["init"]) == 0
    first = (tmp_path / "my-business.toml").read_text(encoding="utf-8")
    assert cli.main(["init"]) == 2
    err = capsys.readouterr().err
    assert "already exists" in err
    assert (tmp_path / "my-business.toml").read_text(encoding="utf-8") == first
    assert cli.main(["init", "--force"]) == 0


def test_init_unknown_pack_exits_2() -> None:
    """An unknown --pack is rejected by the argument parser."""
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["init", "--pack", "no-such-pack"])
    assert excinfo.value.code == 2


def test_init_bad_business_name(tmp_path, monkeypatch, capsys) -> None:
    """A business name with quotes is rejected, and nothing is written."""
    monkeypatch.chdir(tmp_path)
    assert cli.main(["init", "--name", 'Bad "Name']) == 2
    assert not (tmp_path / "my-business.toml").exists()
    assert "business.name" in capsys.readouterr().err


def test_init_creates_parent_directories(tmp_path, monkeypatch) -> None:
    """``--output`` in a missing subdirectory creates it."""
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "business" / "pack.toml"
    assert cli.main(["init", "--output", str(output)]) == 0
    assert load_pack(output).name == "BrightSmile Dental"


def test_init_help_lists_packs(capsys) -> None:
    """``first60 init --help`` names the command and its options."""
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["init", "--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "--pack" in out
    assert "--output" in out
    assert "--force" in out


def test_summary_accepts_pack_file(tmp_path, capsys) -> None:
    """``summary --pack-file`` runs the daily summary on a scaffolded pack."""
    pack_file = tmp_path / "acme.toml"
    assert (
        cli.main(
            [
                "init",
                "--pack",
                "dental",
                "--name",
                "Acme Dental",
                "--output",
                str(pack_file),
            ]
        )
        == 0
    )
    db = tmp_path / "acme.db"
    assert cli.main(["summary", "--pack-file", str(pack_file), "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "Daily summary - Acme Dental" in out
    assert "BOOKED: 0" in out


def test_pack_and_pack_file_are_mutually_exclusive(tmp_path) -> None:
    """Passing both --pack and --pack-file is an error, not a silent win."""
    pack_file = tmp_path / "acme.toml"
    assert cli.main(["init", "--pack", "dental", "--output", str(pack_file)]) == 0
    with pytest.raises(SystemExit):
        cli.main(["summary", "--pack", "dental", "--pack-file", str(pack_file)])


def test_find_packs_dir_prefers_installed_layout(tmp_path) -> None:
    """A packs/ directory inside the package dir wins over the repo root."""
    installed = tmp_path / "site-packages" / "first60"
    packs = installed / "packs"
    packs.mkdir(parents=True)
    shutil.copy(PACKS_DIR / "dental.toml", packs / "dental.toml")
    assert _find_packs_dir(installed) == packs


def test_find_packs_dir_falls_back_to_repo(tmp_path) -> None:
    """Without packs/ inside the package dir, the repo root is used."""
    assert _find_packs_dir(tmp_path) == PACKS_DIR


def test_builtin_pack_names() -> None:
    """The five shipped packs are all loadable by name."""
    from first60.config import builtin_pack_names, load_builtin_pack

    names = builtin_pack_names()
    assert names == ["clinic", "dental", "med-spa", "plumber", "real-estate"]
    for name in names:
        assert load_builtin_pack(name).vertical == name
