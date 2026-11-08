"""Command-line entry points for First60.

Build step 1 (skeleton): only the parser, ``--version`` and ``--help``
work. The ``demo``, ``serve``, ``summary`` and ``init`` commands land in
later build steps and currently report that they are not built yet.
"""

from __future__ import annotations

import argparse
import sys

from first60 import __version__

_COMMANDS = ("demo", "serve", "summary", "init")


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the ``first60`` command."""
    parser = argparse.ArgumentParser(
        prog="first60",
        description=(
            "First60: an open-source text-first AI receptionist for "
            "service businesses. Every text enquiry gets a first reply "
            "with a next step inside 60 seconds."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"first60 {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    demo_parser = subparsers.add_parser(
        "demo",
        help="Run the zero-credential demo scenario (build step 6).",
    )
    demo_parser.add_argument(
        "--interactive",
        action="store_true",
        help="Open the console channel and play the customer yourself.",
    )
    subparsers.add_parser(
        "serve",
        help="Serve the webhook channel (build step 5).",
    )
    subparsers.add_parser(
        "summary",
        help="Print the daily pipeline summary (build step 6).",
    )
    subparsers.add_parser(
        "init",
        help="Create a starter business pack (build step 7).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command in _COMMANDS:
        print(
            f"first60 {args.command}: not built yet "
            "(see the build steps in DESIGN.md section 14).",
            file=sys.stderr,
        )
        return 2
    parser.error(f"unknown command: {args.command}")
    return 2
