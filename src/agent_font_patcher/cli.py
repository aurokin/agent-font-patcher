from __future__ import annotations

import argparse
from pathlib import Path

from agent_font_patcher.manifest import Manifest, ManifestError, load_manifest
from agent_font_patcher.scanner import scan_fonts


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
    subparsers = parser.add_subparsers(dest="command")

    manifest_parser = subparsers.add_parser(
        "manifest",
        help="Inspect the packaged codepoint manifest.",
    )
    manifest_parser.add_argument(
        "--path",
        type=Path,
        help="Load a manifest from this path instead of the packaged manifest.",
    )
    manifest_parser.add_argument(
        "--list",
        action="store_true",
        help="List every icon in the manifest.",
    )
    manifest_parser.set_defaults(handler=handle_manifest)

    scan_parser = subparsers.add_parser(
        "scan",
        help="Find likely installed Nerd Font files.",
    )
    scan_parser.add_argument(
        "--font-dir",
        action="append",
        type=Path,
        help="Directory to scan. Can be passed more than once.",
    )
    scan_parser.set_defaults(handler=handle_scan)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "handler"):
        parser.print_help()
        return 0
    try:
        return args.handler(args)
    except ManifestError as error:
        parser.error(str(error))
    return 0


def handle_manifest(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.path)
    if args.list:
        print_manifest_icons(manifest)
    else:
        print_manifest_summary(manifest)
    return 0


def print_manifest_summary(manifest: Manifest) -> None:
    print(f"project: {manifest.project}")
    print(f"manifest: {manifest.manifest_version}")
    print(f"schema: {manifest.schema_version}")
    print(f"range: {manifest.range_start}-{manifest.range_end}")
    print(f"icons: {len(manifest.icons)}")
    print("blocks:")
    for block in manifest.blocks:
        print(f"  {block.name}: {block.start}-{block.end}")


def print_manifest_icons(manifest: Manifest) -> None:
    for icon in manifest.icons:
        aliases = f" aliases={','.join(icon.aliases)}" if icon.aliases else ""
        status = f" status={icon.asset_status}"
        print(
            f"{icon.codepoint} {icon.character} {icon.id} "
            f"({icon.display_name}){aliases}{status}"
        )


def handle_scan(args: argparse.Namespace) -> int:
    candidates = scan_fonts(args.font_dir)
    if not candidates:
        print("No likely Nerd Font files found.")
        return 0
    for candidate in candidates:
        writable = "writable" if candidate.is_writable else "read-only"
        name = candidate.full_name or candidate.family or candidate.path.stem
        print(f"{candidate.path}\n  name: {name}\n  access: {writable}\n  reason: {candidate.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
