"""Smoke tests: the package imports and the CLI entry points work."""

from __future__ import annotations

import subprocess
import sys

import pytest

import first60
from first60.cli import main


def test_package_imports_and_version() -> None:
    """The package imports and reports version 0.1.0."""
    assert first60.__version__ == "0.1.0"


def test_subpackages_import() -> None:
    """The step 1 package layout imports (stubs included)."""
    import first60.calendar
    import first60.channels
    import first60.pipeline
    import first60.respond
    import first60.store

    assert first60.calendar is not None
    assert first60.channels is not None
    assert first60.pipeline is not None
    assert first60.respond is not None
    assert first60.store is not None


def test_cli_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    """``first60 --version`` prints the version and exits 0."""
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "0.1.0" in captured.out


def test_cli_no_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    """Running ``first60`` with no command prints help and exits 0."""
    assert main([]) == 0
    captured = capsys.readouterr()
    assert "first60" in captured.out


def test_module_entry_point_help() -> None:
    """``python -m first60 --help`` works in a fresh process."""
    result = subprocess.run(
        [sys.executable, "-m", "first60", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "first60" in result.stdout
