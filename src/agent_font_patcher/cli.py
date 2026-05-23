from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-font-patcher",
        description="Patch Nerd Fonts-compatible fonts with agent tooling glyphs.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="agent-font-patcher 0.1.0",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

