"""Command-line entry points for First60.

Build step 5 wires the ``serve`` command (the webhook server over
the real engine). The ``demo``, ``summary`` and ``init`` commands
land in later build steps and currently report that they are not
built yet.
"""

from __future__ import annotations

import argparse
import sys

from first60 import __version__
from first60.engine import WRITE_MODES

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
    serve_parser = subparsers.add_parser(
        "serve",
        help="Serve the webhook channel (build step 5).",
    )
    serve_parser.add_argument(
        "--pack",
        default="dental",
        help="Business pack to serve (default: dental).",
    )
    serve_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Interface to bind (default: 127.0.0.1).",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port to listen on (default: 8765).",
    )
    serve_parser.add_argument(
        "--mode",
        default="demo",
        choices=WRITE_MODES,
        help="Write mode: demo or direct send; dry_run and approval "
        "withhold sends (default: demo).",
    )
    serve_parser.add_argument(
        "--db",
        default="first60.db",
        help="SQLite store file (default: first60.db).",
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


def _serve(args: argparse.Namespace) -> int:
    """Run the webhook server; return a process exit code."""
    from first60.calendar.local import LocalCalendar
    from first60.channels.webhook import WebhookChannel
    from first60.config import load_builtin_pack
    from first60.engine import ReceptionEngine
    from first60.respond.rules import RuleResponder
    from first60.server import create_server
    from first60.store.sqlite import SQLiteStore

    pack = load_builtin_pack(args.pack)
    store = SQLiteStore(args.db)
    try:
        engine = ReceptionEngine(
            pack=pack,
            store=store,
            calendar=LocalCalendar(store, pack),
            responder=RuleResponder(),
            channel=WebhookChannel(),
            write_mode=args.mode,
        )
        server = create_server(engine, args.host, args.port)
        print(
            f"first60 serving {pack.name} on "
            f"http://{args.host}:{args.port} (mode: {args.mode})"
        )
        print('POST /message  {"sender": ..., "text": ...}')
        print("GET  /status   pipeline summary")
        print("GET  /         demo chat page")
        print("Press Ctrl-C to stop.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nfirst60 stopped.")
        return 0
    finally:
        store.close()


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "serve":
        return _serve(args)
    if args.command in _COMMANDS:
        print(
            f"first60 {args.command}: not built yet "
            "(see the build steps in DESIGN.md section 14).",
            file=sys.stderr,
        )
        return 2
    parser.error(f"unknown command: {args.command}")
    return 2
