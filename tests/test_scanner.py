from __future__ import annotations

import tempfile
import struct
import unittest
import zlib
from unittest import mock
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, TTFont

from agent_font_patcher.scanner import (
    default_font_dirs,
    discover_font_files,
    inspect_font,
    read_font_codepoints,
    scan_fonts,
)


class ScannerTest(unittest.TestCase):
    def test_default_font_dirs_for_macos(self) -> None:
        dirs = default_font_dirs("darwin")

        self.assertIn(Path.home() / "Library" / "Fonts", dirs)
        self.assertIn(Path("/Library/Fonts"), dirs)

    def test_default_font_dirs_for_windows_includes_user_fonts(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {"LOCALAPPDATA": r"C:\Users\Agent\AppData\Local", "WINDIR": r"C:\Windows"},
        ):
            dirs = default_font_dirs("win32")

        self.assertIn(Path(r"C:\Users\Agent\AppData\Local") / "Microsoft" / "Windows" / "Fonts", dirs)
        self.assertIn(Path(r"C:\Windows") / "Fonts", dirs)

    def test_default_font_dirs_for_linux_honors_xdg_data_home(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {"XDG_DATA_HOME": "/tmp/xdg-data", "XDG_DATA_DIRS": "/opt/share:/usr/share"},
        ):
            dirs = default_font_dirs("linux")

        self.assertEqual(dirs[0], Path("/tmp/xdg-data/fonts"))
        self.assertIn(Path("/opt/share/fonts"), dirs)
        self.assertIn(Path("/usr/share/fonts"), dirs)

    def test_default_font_dirs_for_linux_treats_empty_xdg_values_as_unset(self) -> None:
        with mock.patch.dict("os.environ", {"XDG_DATA_HOME": "", "XDG_DATA_DIRS": ""}):
            dirs = default_font_dirs("linux")

        self.assertEqual(dirs[0], Path.home() / ".local/share/fonts")
        self.assertIn(Path("/usr/local/share/fonts"), dirs)
        self.assertIn(Path("/usr/share/fonts"), dirs)

    def test_discover_font_files_filters_extensions_and_dedupes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            font = root / "Example.ttf"
            ignored = root / "README.md"
            font.write_bytes(b"not a real font")
            ignored.write_text("ignore", encoding="utf-8")

            self.assertEqual(discover_font_files([root, root]), [font])

    def test_scan_fonts_finds_likely_nerd_font(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            font_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(font_path, family="Example Nerd Font", full_name="Example Nerd Font")

            candidates = scan_fonts([root])

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].family, "Example Nerd Font")
        self.assertTrue(candidates[0].is_likely_nerd_font)
        self.assertTrue(candidates[0].is_readable)

    def test_read_font_codepoints_reports_cmap_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            font_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                font_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font",
                extra_codepoints={0x100000: "agent_icon"},
            )

            result = read_font_codepoints(font_path)

        self.assertIsNone(result.error)
        self.assertIn(32, result.codepoints)
        self.assertIn(0x100000, result.codepoints)

    def test_scan_fonts_finds_nerd_font_in_second_ttc_face(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            regular_path = root / "Regular.ttf"
            nerd_path = root / "Nerd.ttf"
            collection_path = root / "Collection.ttc"
            _write_minimal_font(regular_path, family="Example", full_name="Example Regular")
            _write_minimal_font(nerd_path, family="Example Nerd Font", full_name="Example Nerd Font")
            collection = TTCollection()
            collection.fonts = [TTFont(regular_path), TTFont(nerd_path)]
            collection.save(collection_path)
            regular_path.unlink()
            nerd_path.unlink()

            candidates = scan_fonts([root])

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].family, "Example Nerd Font")

    def test_read_font_codepoints_uses_selected_ttc_face(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            regular_path = root / "Regular.ttf"
            nerd_path = root / "Nerd.ttf"
            collection_path = root / "Collection.ttc"
            _write_minimal_font(
                regular_path,
                family="Example",
                full_name="Example Regular",
                extra_codepoints={0x100000: "agent_icon"},
            )
            _write_minimal_font(nerd_path, family="Example Nerd Font", full_name="Example Nerd Font")
            collection = TTCollection()
            collection.fonts = [TTFont(regular_path), TTFont(nerd_path)]
            collection.save(collection_path)
            regular_path.unlink()
            nerd_path.unlink()

            result = read_font_codepoints(collection_path)

        self.assertIsNone(result.error)
        self.assertNotIn(0x100000, result.codepoints)

    def test_read_font_codepoints_treats_empty_ttc_as_unreadable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            collection_path = Path(tmp) / "Empty.ttc"
            collection = TTCollection()
            collection.fonts = []
            collection.save(collection_path)

            result = read_font_codepoints(collection_path)

        self.assertIsNotNone(result.error)
        self.assertIn("empty font collection", result.error)

    def test_scan_fonts_ignores_non_nerd_font(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            font_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(font_path, family="Example", full_name="Example Regular")

            candidates = scan_fonts([root])

        self.assertEqual(candidates, [])

    def test_inspect_font_reports_unreadable_font(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_path = Path(tmp) / "BrokenNerdFont-Regular.ttf"
            font_path.write_bytes(b"not a font")

            candidate = inspect_font(font_path)

        self.assertFalse(candidate.is_likely_nerd_font)
        self.assertFalse(candidate.is_readable)
        self.assertIn("unreadable font", candidate.reason)

    def test_metadata_struct_errors_are_treated_as_unreadable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            font_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(font_path, family="Example Nerd Font", full_name="Example Nerd Font")

            with mock.patch(
                "agent_font_patcher.scanner._candidate_from_font",
                side_effect=struct.error("bad name table"),
            ):
                candidates = scan_fonts([root])

        self.assertEqual(candidates, [])

    def test_metadata_zlib_errors_are_treated_as_unreadable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            font_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(font_path, family="Example Nerd Font", full_name="Example Nerd Font")

            with mock.patch(
                "agent_font_patcher.scanner._candidate_from_font",
                side_effect=zlib.error("bad compressed name table"),
            ):
                candidates = scan_fonts([root])

        self.assertEqual(candidates, [])

    def test_truncated_sfont_parser_errors_are_treated_as_unreadable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            font_path = root / "Broken.ttf"
            font_path.write_bytes(b"\x00\x01\x00\x00")

            candidates = scan_fonts([root])

        self.assertEqual(candidates, [])

    def test_truncated_ttc_parser_errors_are_treated_as_unreadable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            font_path = root / "Broken.ttc"
            font_path.write_bytes(b"ttcf\x00\x01\x00\x00")

            candidates = scan_fonts([root])

        self.assertEqual(candidates, [])


def _write_minimal_font(
    path: Path,
    family: str,
    full_name: str,
    extra_codepoints: dict[int, str] | None = None,
) -> None:
    extra_codepoints = extra_codepoints or {}
    glyph_order = [".notdef", "space", *extra_codepoints.values()]
    units_per_em = 1000
    builder = FontBuilder(units_per_em, isTTF=True)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap({32: "space", **extra_codepoints})

    glyphs = {}
    metrics = {}
    for glyph_name in glyph_order:
        pen = TTGlyphPen(None)
        glyphs[glyph_name] = pen.glyph()
        metrics[glyph_name] = (500, 0)

    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics(metrics)
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupOS2()
    builder.setupPost()
    builder.setupNameTable(
        {
            "familyName": family,
            "styleName": "Regular",
            "uniqueFontIdentifier": f"{family} Regular",
            "fullName": full_name,
            "psName": family.replace(" ", "") + "-Regular",
        }
    )
    builder.save(path)
