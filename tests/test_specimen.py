from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_font_patcher.manifest import codepoint_to_int, load_manifest
from agent_font_patcher.specimen import SpecimenError, default_specimen_path, generate_html_specimen
from tests.test_patcher import _available_icon_manifest
from tests.test_scanner import _write_minimal_font


class SpecimenTest(unittest.TestCase):
    def test_generate_html_specimen_embeds_font_and_reports_glyphs(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            font_path = root / "ExampleNerdFont-Regular.ttf"
            output_path = root / "specimen.html"
            _write_minimal_font(
                font_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
                extra_codepoints={0x100000: "agent.test_icon"},
            )

            result = generate_html_specimen(font_path, output_path, manifest)
            html = output_path.read_text(encoding="utf-8")

        self.assertEqual(result.output_path, output_path)
        self.assertEqual(result.present_count, 1)
        self.assertEqual(result.total_count, 1)
        self.assertIn("@font-face", html)
        self.assertIn("data:font/ttf;base64,", html)
        self.assertIn("Test Icon", html)
        self.assertIn("U+100000", html)
        self.assertIn("&#x100000;", html)
        self.assertIn("present", html)

    def test_generate_html_specimen_marks_missing_glyphs(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            font_path = root / "ExampleNerdFont-Regular.ttf"
            output_path = root / "specimen.html"
            _write_minimal_font(
                font_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            result = generate_html_specimen(font_path, output_path, manifest)
            html = output_path.read_text(encoding="utf-8")

        self.assertEqual(result.present_count, 0)
        self.assertIn("missing", html)

    def test_generate_html_specimen_uses_full_packaged_manifest(self) -> None:
        manifest = load_manifest()
        first_icon = manifest.icons[0]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            font_path = root / "ExampleNerdFont-Regular.ttf"
            output_path = root / "specimen.html"
            _write_minimal_font(
                font_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
                extra_codepoints={codepoint_to_int(first_icon.codepoint): first_icon.id},
            )

            result = generate_html_specimen(font_path, output_path)
            html = output_path.read_text(encoding="utf-8")

        self.assertEqual(result.present_count, 1)
        self.assertEqual(result.total_count, len(manifest.icons))
        self.assertIn(first_icon.display_name, html)
        self.assertIn(first_icon.asset_status, html)
        self.assertIn("Agent Glyphs", html)

    def test_default_specimen_path_uses_font_stem(self) -> None:
        font_path = Path("/fonts/Example.ttf")

        self.assertEqual(
            default_specimen_path(font_path),
            Path("/fonts/Example-agent-specimen.html"),
        )
        self.assertEqual(
            default_specimen_path(font_path, Path("/out")),
            Path("/out/Example-agent-specimen.html"),
        )

    def test_generate_html_specimen_rejects_source_font_output(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            font_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                font_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            original_bytes = font_path.read_bytes()

            with self.assertRaisesRegex(SpecimenError, "source font"):
                generate_html_specimen(font_path, font_path, manifest)

            self.assertEqual(font_path.read_bytes(), original_bytes)

    def test_generate_html_specimen_rejects_symlink_output(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            font_path = root / "ExampleNerdFont-Regular.ttf"
            output_path = root / "specimen.html"
            _write_minimal_font(
                font_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            output_path.symlink_to(root / "elsewhere.html")

            with self.assertRaisesRegex(SpecimenError, "symlink"):
                generate_html_specimen(font_path, output_path, manifest)

    def test_generate_html_specimen_refuses_existing_output(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            font_path = root / "ExampleNerdFont-Regular.ttf"
            output_path = root / "specimen.html"
            _write_minimal_font(
                font_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            output_path.write_text("existing", encoding="utf-8")

            with self.assertRaisesRegex(SpecimenError, "already exists"):
                generate_html_specimen(font_path, output_path, manifest)

    def test_generate_html_specimen_wraps_output_parent_errors(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            font_path = root / "ExampleNerdFont-Regular.ttf"
            blocked_parent = root / "blocked"
            output_path = blocked_parent / "specimen.html"
            _write_minimal_font(
                font_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            blocked_parent.write_text("not a directory", encoding="utf-8")

            with self.assertRaisesRegex(SpecimenError, "unable to write specimen"):
                generate_html_specimen(font_path, output_path, manifest)

    def test_generate_html_specimen_rejects_font_collections(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            font_path = root / "Collection.ttc"
            output_path = root / "specimen.html"
            font_path.write_bytes(b"ttcf\x00\x01\x00\x00")

            with self.assertRaisesRegex(SpecimenError, "collections"):
                generate_html_specimen(font_path, output_path, manifest)

    def test_generate_html_specimen_rejects_renamed_font_collections(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            font_path = root / "Collection.ttf"
            output_path = root / "specimen.html"
            font_path.write_bytes(b"ttcf\x00\x01\x00\x00")

            with self.assertRaisesRegex(SpecimenError, "collections"):
                generate_html_specimen(font_path, output_path, manifest)


if __name__ == "__main__":
    unittest.main()
