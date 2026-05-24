from __future__ import annotations

import argparse
from pathlib import Path

from agent_font_patcher.inspector import FontInspection, inspect_agent_font
from agent_font_patcher.manifest import Manifest, ManifestError, load_manifest
from agent_font_patcher.patcher import PatchError, PatchResult, patch_font_branch
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

    patch_parser = subparsers.add_parser(
        "patch",
        help="Create a branch-off font from an explicit glyph manifest.",
    )
    patch_parser.add_argument("font_path", type=Path)
    patch_parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory where the patched branch-off font will be written.",
    )
    patch_parser.add_argument(
        "--manifest-path",
        required=True,
        type=Path,
        help="Load a manifest with available glyph assets.",
    )
    patch_parser.add_argument(
        "--use-placeholder-glyphs",
        action="store_true",
        help="Use generated placeholder glyphs until SVG asset ingestion is available.",
    )
    patch_parser.set_defaults(handler=handle_patch)

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Inspect one font and report agent glyph coverage.",
    )
    inspect_parser.add_argument("font_path", type=Path)
    inspect_parser.add_argument(
        "--manifest-path",
        type=Path,
        help="Load a manifest from this path instead of the packaged manifest.",
    )
    inspect_parser.set_defaults(handler=handle_inspect)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "handler"):
        parser.print_help()
        return 0
    try:
        return args.handler(args)
    except (ManifestError, PatchError) as error:
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


def handle_patch(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest_path)
    result = patch_font_branch(
        args.font_path,
        args.output_dir,
        manifest,
        use_placeholder_glyphs=args.use_placeholder_glyphs,
    )
    print_patch_result(result)
    return 0


def print_patch_result(result: PatchResult) -> None:
    print(f"source: {result.source_path}")
    print(f"output: {result.output_path}")
    print(f"manifest: {result.metadata['manifest_version']}")
    print(f"placeholder_glyphs: {'yes' if result.metadata['placeholder_glyphs'] else 'no'}")
    print(f"patched_codepoints: {len(result.patched_codepoints)}")
    for codepoint in result.patched_codepoints:
        print(f"  {codepoint}")


def handle_inspect(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest_path)
    inspection = inspect_agent_font(args.font_path, manifest)
    print_font_inspection(inspection)
    return 1 if inspection.codepoints_error or not inspection.candidate.is_readable else 0


def print_font_inspection(inspection: FontInspection) -> None:
    candidate = inspection.candidate
    print(f"path: {candidate.path}")
    print(f"name: {candidate.full_name or candidate.family or candidate.path.stem}")
    print(f"family: {candidate.family or 'unknown'}")
    print(f"subfamily: {candidate.subfamily or 'unknown'}")
    print(f"postscript: {candidate.postscript_name or 'unknown'}")
    print(f"access: {'writable' if candidate.is_writable else 'read-only'}")
    print(f"likely_nerd_font: {'yes' if candidate.is_likely_nerd_font else 'no'}")
    print(f"reason: {candidate.reason}")
    print(f"manifest: {inspection.manifest.manifest_version}")
    print(f"patched: {'yes' if inspection.patch_metadata else 'no'}")
    if inspection.patch_metadata:
        print(f"patcher_version: {inspection.patch_metadata.get('patcher_version', 'unknown')}")
        print(f"patched_manifest: {inspection.patch_metadata.get('manifest_version', 'unknown')}")
        print(f"placeholder_glyphs: {inspection.patch_metadata.get('placeholder_glyphs', 'unknown')}")
        print(f"patched_range: {inspection.patch_metadata.get('codepoint_range', 'unknown')}")
        print(f"patched_icons: {len(inspection.patch_metadata.get('patched_codepoints', []))}")
        print(f"source_font: {inspection.patch_metadata.get('source_font_name', 'unknown')}")
        print(f"source_hash: {inspection.patch_metadata.get('source_font_hash', 'unknown')}")
    if inspection.codepoints_error:
        print(f"agent_codepoints: unreadable ({inspection.codepoints_error})")
        return

    present = inspection.present_icons
    missing = inspection.missing_icons
    reserved = inspection.occupied_reserved_codepoints
    legacy_present = len(present) + len(reserved)
    legacy_total = len(inspection.icon_coverage) + len(inspection.reserved_coverage)
    print(f"agent_codepoints: {legacy_present}/{legacy_total} present")
    print(f"available_agent_glyphs: {len(present)}/{len(inspection.icon_coverage)} present")
    print(f"reserved_codepoints: {len(reserved)}/{len(inspection.reserved_coverage)} occupied")
    if present:
        print("present:")
        for coverage in present:
            print(f"  {coverage.icon.codepoint} {coverage.icon.id}")
    if reserved:
        print("reserved_occupied:")
        for coverage in reserved:
            print(f"  {coverage.icon.codepoint} {coverage.icon.id}")
    if missing:
        print("missing:")
        for coverage in missing:
            print(f"  {coverage.icon.codepoint} {coverage.icon.id}")


if __name__ == "__main__":
    raise SystemExit(main())
