from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_font_patcher.inspector import inspect_agent_font
from agent_font_patcher.manifest import load_manifest
from tests.test_scanner import _write_minimal_font


class InspectorTest(unittest.TestCase):
    def test_inspect_agent_font_reports_manifest_codepoint_coverage(self) -> None:
        manifest = load_manifest()
        first_icon = manifest.icons[0]
        codepoint = int(first_icon.codepoint[2:], 16)

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
        self.assertEqual(len(inspection.present_icons), 1)
        self.assertEqual(inspection.present_icons[0].icon.id, first_icon.id)

    def test_inspect_agent_font_reports_codepoint_read_errors(self) -> None:
        manifest = load_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            font_path = Path(tmp) / "Broken.ttf"
            font_path.write_bytes(b"not a font")

            inspection = inspect_agent_font(font_path, manifest)

        self.assertIsNotNone(inspection.codepoints_error)
        self.assertEqual(inspection.present_icons, ())

