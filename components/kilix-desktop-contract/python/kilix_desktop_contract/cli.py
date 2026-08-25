"""Command-line interface for contract helpers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .actions import ActionError, parse_action
from .catalog import sanitize_catalog_text
from .jsonio import DocumentError, load_json
from .validation import errors_for, validators


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kilix-desktop-contract")
    commands = parser.add_subparsers(dest="command", required=True)
    validate_parser = commands.add_parser("validate")
    validate_parser.add_argument("kind")
    validate_parser.add_argument("document", type=Path)
    action_parser = commands.add_parser("parse-action")
    action_parser.add_argument("action")
    sanitize_parser = commands.add_parser("sanitize")
    sanitize_parser.add_argument("text")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "validate":
            document = load_json(arguments.document)
            errors = errors_for(arguments.kind, document, validators())
            if errors:
                for error in errors:
                    print(error, file=sys.stderr)
                return 3
            return 0
        if arguments.command == "parse-action":
            print(json.dumps(parse_action(arguments.action).as_dict(), sort_keys=True))
            return 0
        if arguments.command == "sanitize":
            print(sanitize_catalog_text(arguments.text))
            return 0
    except (ActionError, DocumentError, OSError, UnicodeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 3
    return 70


if __name__ == "__main__":
    raise SystemExit(main())
