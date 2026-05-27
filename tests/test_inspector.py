from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fontTools.ttLib import TTFont

from agent_font_patcher.cli import handle_inspect
from agent_font_patcher.inspector import FontInspection, inspect_agent_font
from agent_font_patcher.manifest import Manifest, load_manifest, parse_manifest
from agent_font_patcher.scanner import FontCandidate
from tests.test_scanner import _write_minimal_font


class InspectorTest(unittest.TestCase):
    def test_inspect_agent_font_reports_manifest_codepoint_coverage(self) -> None:
        manifest = load_manifest()
        reserved_icon = next(icon for icon in manifest.icons if icon.asset_status == "reserved")
        codepoint = int(reserved_icon.codepoint[2:], 16)

        with tempfile.TemporaryDirectory() as tmp:
            font_path = Path(tmp) / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                font_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font",
                extra_codepoints={codepoint: "agent_icon"},
            )

            inspection = inspect_agent_font(font_path, manifest)

        self.assertIsNone(inspection.codepoints_error)
        self.assertTrue(inspection.candidate.is_likely_nerd_font)
        self.assertEqual(inspection.present_icons, ())
        self.assertEqual(len(inspection.occupied_reserved_codepoints), 1)
        self.assertEqual(inspection.occupied_reserved_codepoints[0].icon.id, reserved_icon.id)

    def test_inspect_agent_font_reports_codepoint_read_errors(self) -> None:
        manifest = load_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            font_path = Path(tmp) / "Broken.ttf"
            font_path.write_bytes(b"not a font")

            inspection = inspect_agent_font(font_path, manifest)

        self.assertIsNotNone(inspection.codepoints_error)
        self.assertEqual(inspection.present_icons, ())

    def test_inspect_exit_fails_when_metadata_is_unreadable_but_cmap_is_readable(self) -> None:
        manifest = load_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            font_path = Path(tmp) / "NoName.ttf"
            _write_minimal_font(font_path, family="Example Nerd Font", full_name="Example Nerd Font")
            font = TTFont(font_path)
            del font["name"]
            font.save(font_path)
            font.close()

            inspection = inspect_agent_font(font_path, manifest)

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = handle_inspect(SimpleNamespace(manifest_path=None, font_path=font_path))

        self.assertFalse(inspection.candidate.is_readable)
        self.assertIsNone(inspection.codepoints_error)
        self.assertEqual(exit_code, 1)

    def test_inspect_output_reports_reserved_hits_separately(self) -> None:
        manifest = load_manifest()
        reserved_icon = next(icon for icon in manifest.icons if icon.asset_status == "reserved")
        codepoint = int(reserved_icon.codepoint[2:], 16)

        with tempfile.TemporaryDirectory() as tmp:
            font_path = Path(tmp) / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                font_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font",
                extra_codepoints={codepoint: "reserved_slot"},
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = handle_inspect(SimpleNamespace(manifest_path=None, font_path=font_path))

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        total_icons = len(manifest.icons)
        reserved_icons = sum(
            1 for icon in manifest.icons if icon.asset_status in {"reserved", "deprecated"}
        )
        available_icons = sum(1 for icon in manifest.icons if icon.asset_status == "available")
        self.assertIn(f"agent_codepoints: 1/{total_icons} present", output)
        self.assertIn(f"available_agent_glyphs: 0/{available_icons} present", output)
        self.assertIn(f"reserved_codepoints: 1/{reserved_icons} occupied", output)
        self.assertIn(f"{reserved_icon.codepoint} {reserved_icon.id}", output)

    def test_deprecated_manifest_entries_count_as_reserved_occupancy(self) -> None:
        manifest = _single_icon_manifest(asset_status="deprecated")

        with tempfile.TemporaryDirectory() as tmp:
            font_path = Path(tmp) / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                font_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font",
                extra_codepoints={0x100000: "deprecated_slot"},
            )

            inspection = inspect_agent_font(font_path, manifest)

        self.assertEqual(inspection.present_icons, ())
        self.assertEqual(len(inspection.occupied_reserved_codepoints), 1)

    def test_font_inspection_accepts_original_positional_shape(self) -> None:
        manifest = load_manifest()
        candidate = FontCandidate(
            Path("Example.ttf"),
            "Example",
            "Regular",
            "Example Regular",
            "Example-Regular",
            True,
            True,
            "reason",
        )

        inspection = FontInspection(candidate, manifest, (), None)

        self.assertEqual(inspection.codepoints_error, None)
        self.assertEqual(inspection.reserved_coverage, ())


def _single_icon_manifest(asset_status: str) -> Manifest:
    return parse_manifest(
        {
            "schema_version": 1,
            "manifest_version": "test",
            "project": "agent-font-patcher",
            "range": {
                "start": "U+100000",
                "end": "U+1000FF",
                "description": "test",
            },
            "blocks": [
                {
                    "name": "providers",
                    "start": "U+100000",
                    "end": "U+10003F",
                    "description": "test",
                }
            ],
            "icons": [
                {
                    "id": "test-icon",
                    "display_name": "Test Icon",
                    "aliases": [],
                    "category": "providers",
                    "codepoint": "U+100000",
                    "asset_status": asset_status,
                }
            ],
        }
    )
