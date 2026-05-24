from __future__ import annotations

import contextlib
import io
import json
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fontTools.ttLib import TTCollection, TTFont
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable

from agent_font_patcher.cli import handle_inspect, handle_patch
from agent_font_patcher.inspector import inspect_agent_font
from agent_font_patcher.manifest import Manifest, parse_manifest
from agent_font_patcher.patcher import (
    PatchError,
    _best_unicode_cmap,
    patch_font_branch,
    read_patch_metadata,
)
from agent_font_patcher.scanner import inspect_font, read_font_codepoints
from tests.test_scanner import _write_minimal_font


class PatcherTest(unittest.TestCase):
    def test_patch_font_branch_writes_renamed_output_with_manifest_glyph(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            output_dir = root / "out"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            source_bytes = source_path.read_bytes()

            result = patch_font_branch(
                source_path,
                output_dir,
                manifest,
                use_placeholder_glyphs=True,
            )
            inspection = inspect_agent_font(result.output_path, manifest)
            output_candidate = inspect_font(result.output_path)
            codepoints = read_font_codepoints(result.output_path)
            metadata = read_patch_metadata(result.output_path)

            self.assertEqual(source_path.read_bytes(), source_bytes)
            self.assertEqual(result.output_path, output_dir / "ExampleNerdFont-Regular-Agent.ttf")
            self.assertEqual(result.patched_codepoints, ("U+100000",))
            self.assertTrue(result.output_path.exists())
            self.assertEqual(output_candidate.family, "Example Agent Nerd Font")
            self.assertIn(32, codepoints.codepoints)
            self.assertIn(0x100000, codepoints.codepoints)
            output_font = TTFont(result.output_path)
            agent_width = output_font["hmtx"].metrics["agent.test_icon"][0]
            space_width = output_font["hmtx"].metrics["space"][0]
            output_font.close()
            self.assertEqual(agent_width, space_width)
            self.assertEqual(len(inspection.present_icons), 1)
            self.assertEqual(inspection.present_icons[0].icon.id, "test-icon")
            self.assertIsNotNone(metadata)
            self.assertEqual(metadata["manifest_version"], "test")
            self.assertEqual(metadata["patched_codepoints"], ["U+100000"])
            self.assertEqual(metadata["glyph_source"], "placeholder")
            self.assertTrue(metadata["placeholder_glyphs"])
            self.assertEqual(inspection.patch_metadata, metadata)

    def test_patch_command_prints_output_path(self) -> None:
        manifest_path_content = _available_icon_manifest_json()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            output_dir = root / "out"
            manifest_path = root / "manifest.json"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            manifest_path.write_text(manifest_path_content, encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = handle_patch(
                    SimpleNamespace(
                        font_path=source_path,
                        output_dir=output_dir,
                        manifest_path=manifest_path,
                        use_placeholder_glyphs=True,
                    )
                )

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn(f"source: {source_path}", output)
        self.assertIn(f"output: {output_dir / 'ExampleNerdFont-Regular-Agent.ttf'}", output)
        self.assertIn("placeholder_glyphs: yes", output)
        self.assertIn("patched_codepoints: 1", output)

    def test_inspect_prints_embedded_patch_range_and_icon_count(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            output_dir = root / "out"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            result = patch_font_branch(
                source_path,
                output_dir,
                manifest,
                use_placeholder_glyphs=True,
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = handle_inspect(
                    SimpleNamespace(manifest_path=None, font_path=result.output_path)
                )

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("patched_manifest: test", output)
        self.assertIn("patched_range: U+100000-U+1000FF", output)
        self.assertIn("patched_icons: 1", output)

    def test_patch_font_branch_requires_explicit_placeholder_mode(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "placeholder"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_other_manifest_projects(self) -> None:
        manifest = parse_manifest({**_available_icon_manifest_raw(), "project": "other-project"})

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "manifest project"):
                patch_font_branch(
                    source_path,
                    root / "out",
                    manifest,
                    use_placeholder_glyphs=True,
                )

    def test_patch_font_branch_rejects_non_private_use_codepoints(self) -> None:
        manifest = _available_icon_manifest(
            codepoint="U+0020",
            range_start="U+0020",
            range_end="U+0020",
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "private-use"):
                patch_font_branch(
                    source_path,
                    root / "out",
                    manifest,
                    use_placeholder_glyphs=True,
                )

    def test_patch_font_branch_rejects_reserved_non_private_use_codepoints(self) -> None:
        manifest = parse_manifest(
            {
                **_available_icon_manifest_raw(),
                "range": {
                    "start": "U+0020",
                    "end": "U+100000",
                    "description": "test",
                },
                "blocks": [
                    {
                        "name": "providers",
                        "start": "U+0020",
                        "end": "U+100000",
                        "description": "test",
                    }
                ],
                "icons": [
                    {
                        "id": "reserved-space",
                        "display_name": "Reserved Space",
                        "aliases": [],
                        "category": "providers",
                        "codepoint": "U+0020",
                        "asset_status": "reserved",
                    },
                    *_available_icon_manifest_raw()["icons"],
                ],
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "private-use"):
                patch_font_branch(
                    source_path,
                    root / "out",
                    manifest,
                    use_placeholder_glyphs=True,
                )

    def test_patch_font_branch_rejects_ranges_that_cross_private_use_gaps(self) -> None:
        manifest = _available_icon_manifest(
            codepoint="U+100000",
            range_start="U+F8FF",
            range_end="U+100000",
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "private-use range"):
                patch_font_branch(
                    source_path,
                    root / "out",
                    manifest,
                    use_placeholder_glyphs=True,
                )

    def test_patch_font_branch_rejects_existing_codepoint_mapping(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
                extra_codepoints={0x100000: "existing_icon"},
            )

            with self.assertRaisesRegex(PatchError, "already maps"):
                patch_font_branch(
                    source_path,
                    root / "out",
                    manifest,
                    use_placeholder_glyphs=True,
                )

    def test_patch_font_branch_rejects_same_name_existing_codepoint_mapping(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
                extra_codepoints={0x100000: "agent.test_icon"},
            )

            with self.assertRaisesRegex(PatchError, "glyph name already exists"):
                patch_font_branch(
                    source_path,
                    root / "out",
                    manifest,
                    use_placeholder_glyphs=True,
                )

    def test_patch_font_branch_rejects_existing_generated_glyph_name(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
                extra_codepoints={0xE001: "agent.test_icon"},
            )

            with self.assertRaisesRegex(PatchError, "glyph name already exists"):
                patch_font_branch(
                    source_path,
                    root / "out",
                    manifest,
                    use_placeholder_glyphs=True,
                )

    def test_patch_font_branch_wraps_missing_source_errors(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "out"

            with self.assertRaisesRegex(PatchError, "unable to read font"):
                patch_font_branch(
                    root / "missing.ttf",
                    output_dir,
                    manifest,
                    use_placeholder_glyphs=True,
                )

            self.assertFalse(output_dir.exists())

    def test_patch_font_branch_wraps_structural_parse_errors(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            font_path = root / "Broken.ttf"
            font_path.write_bytes(b"not a real font")

            with mock.patch(
                "agent_font_patcher.patcher.TTFont",
                side_effect=struct.error("bad sfnt"),
            ):
                with self.assertRaisesRegex(PatchError, "unable to read font"):
                    patch_font_branch(
                        font_path,
                        root / "out",
                        manifest,
                        use_placeholder_glyphs=True,
                    )

    def test_patch_font_branch_wraps_delayed_parser_errors(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with mock.patch(
                "agent_font_patcher.patcher._font_full_name",
                side_effect=struct.error("bad name table"),
            ):
                with self.assertRaisesRegex(PatchError, "unable to patch font"):
                    patch_font_branch(
                        source_path,
                        root / "out",
                        manifest,
                        use_placeholder_glyphs=True,
                    )

    def test_patch_font_branch_refuses_to_overwrite_output(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            output_dir = root / "out"
            output_dir.mkdir()
            (output_dir / "ExampleNerdFont-Regular-Agent.ttf").write_bytes(b"existing")
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "output already exists"):
                patch_font_branch(
                    source_path,
                    output_dir,
                    manifest,
                    use_placeholder_glyphs=True,
                )

    def test_patch_font_branch_refuses_dangling_output_symlink(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            output_dir = root / "out"
            output_dir.mkdir()
            (output_dir / "ExampleNerdFont-Regular-Agent.ttf").symlink_to(root / "elsewhere.ttf")
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "output already exists"):
                patch_font_branch(
                    source_path,
                    output_dir,
                    manifest,
                    use_placeholder_glyphs=True,
                )

    def test_read_patch_metadata_ignores_unrelated_name_record_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_path = Path(tmp) / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                font_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            font = TTFont(font_path)
            font["name"].setName(json.dumps({"owner": "other-tool"}), 256, 3, 1, 0x409)
            font.save(font_path)
            font.close()

            inspection = inspect_agent_font(font_path, _available_icon_manifest())
            metadata = read_patch_metadata(font_path)

        self.assertIsNone(metadata)
        self.assertIsNone(inspection.patch_metadata)

    def test_patch_font_branch_preserves_unrelated_private_name_record(self) -> None:
        manifest = _available_icon_manifest()
        unrelated = json.dumps({"owner": "other-tool"})

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            font = TTFont(source_path)
            font["name"].setName(unrelated, 256, 3, 1, 0x409)
            font.save(source_path)
            font.close()

            result = patch_font_branch(
                source_path,
                root / "out",
                manifest,
                use_placeholder_glyphs=True,
            )
            output_font = TTFont(result.output_path)
            private_values = [
                record.toUnicode()
                for record in output_font["name"].names
                if record.nameID in {256, 257}
                and (record.platformID, record.platEncID, record.langID) == (3, 1, 0x409)
            ]
            output_font.close()

        self.assertIn(unrelated, private_values)
        self.assertIn(result.metadata, [json.loads(value) for value in private_values])

    def test_read_patch_metadata_skips_malformed_private_name_records(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            font = TTFont(source_path)
            font["name"].setName("not json", 256, 1, 0, 0)
            font.save(source_path)
            font.close()

            result = patch_font_branch(
                source_path,
                root / "out",
                manifest,
                use_placeholder_glyphs=True,
            )
            metadata = read_patch_metadata(result.output_path)

        self.assertIsNotNone(metadata)
        self.assertEqual(metadata["project"], "agent-font-patcher")

    def test_read_patch_metadata_treats_parser_errors_as_missing_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_path = Path(tmp) / "Broken.ttf"
            font_path.write_bytes(b"not a font")

            with mock.patch(
                "agent_font_patcher.patcher.TTFont",
                side_effect=struct.error("bad font"),
            ):
                metadata = read_patch_metadata(font_path)

        self.assertIsNone(metadata)

    def test_patch_font_branch_replaces_stale_project_metadata_records(self) -> None:
        manifest = _available_icon_manifest()
        stale_metadata = {
            "project": "agent-font-patcher",
            "patcher_version": "0.0.0",
            "manifest_version": "stale",
            "codepoint_range": "U+100000-U+1000FF",
            "patched_codepoints": ["U+100000"],
            "source_font_name": "Stale",
            "source_font_hash": "sha256:stale",
            "patched_at": "2026-01-01T00:00:00Z",
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            font = TTFont(source_path)
            font["name"].setName(json.dumps(stale_metadata), 256, 1, 0, 0)
            font.save(source_path)
            font.close()

            result = patch_font_branch(
                source_path,
                root / "out",
                manifest,
                use_placeholder_glyphs=True,
            )
            metadata = read_patch_metadata(result.output_path)

        self.assertIsNotNone(metadata)
        self.assertEqual(metadata["manifest_version"], "test")
        self.assertEqual(metadata["source_font_hash"], result.metadata["source_font_hash"])

    def test_patch_font_branch_handles_bmp_private_use_codepoints(self) -> None:
        manifest = _available_icon_manifest(codepoint="U+F000", range_start="U+F000", range_end="U+F0FF")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            result = patch_font_branch(
                source_path,
                root / "out",
                manifest,
                use_placeholder_glyphs=True,
            )
            codepoints = read_font_codepoints(result.output_path)

        self.assertIn(32, codepoints.codepoints)
        self.assertIn(0xF000, codepoints.codepoints)

    def test_patch_font_branch_avoids_duplicate_format_12_cmap_identity(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            font = TTFont(source_path)
            format_13 = CmapSubtable.newSubtable(13)
            format_13.platformID = 3
            format_13.platEncID = 10
            format_13.language = 0
            format_13.cmap = {32: "space"}
            font["cmap"].tables = [format_13]
            font.save(source_path)
            font.close()

            result = patch_font_branch(
                source_path,
                root / "out",
                manifest,
                use_placeholder_glyphs=True,
            )
            codepoints = read_font_codepoints(result.output_path)

        self.assertIn(32, codepoints.codepoints)
        self.assertIn(0x100000, codepoints.codepoints)

    def test_format_12_seed_ignores_format_13_when_normal_cmap_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            font = TTFont(source_path)
            format_13 = CmapSubtable.newSubtable(13)
            format_13.platformID = 3
            format_13.platEncID = 10
            format_13.language = 0
            format_13.cmap = {32: ".notdef"}
            font["cmap"].tables.append(format_13)
            best_cmap = _best_unicode_cmap(font)
            font.close()

        self.assertEqual(best_cmap[32], "space")

    def test_patch_font_branch_handles_non_ascii_family_names(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Ā Nerd Font",
                full_name="Ā Nerd Font Regular",
            )

            result = patch_font_branch(
                source_path,
                root / "out",
                manifest,
                use_placeholder_glyphs=True,
            )
            candidate = inspect_font(result.output_path)

        self.assertEqual(candidate.family, "Ā Agent Nerd Font")
        self.assertIsNotNone(candidate.postscript_name)
        self.assertTrue(candidate.postscript_name.isascii())

    def test_patch_font_branch_rejects_collections_for_now(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "Collection.ttc"
            source_path.write_bytes(b"ttcf\x00\x01\x00\x00")

            with self.assertRaisesRegex(PatchError, "collections"):
                patch_font_branch(
                    source_path,
                    Path(tmp) / "out",
                    manifest,
                    use_placeholder_glyphs=True,
                )

    def test_patch_font_branch_rejects_collections_by_header(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            regular_path = root / "Regular.ttf"
            collection_path = root / "Collection.otc"
            _write_minimal_font(
                regular_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            collection = TTCollection()
            collection.fonts = [TTFont(regular_path)]
            collection.save(collection_path)
            regular_path.unlink()

            with self.assertRaisesRegex(PatchError, "collections"):
                patch_font_branch(
                    collection_path,
                    root / "out",
                    manifest,
                    use_placeholder_glyphs=True,
                )

    def test_patch_font_branch_rejects_manifest_without_available_assets(self) -> None:
        manifest = parse_manifest(
            {
                **_available_icon_manifest_raw(),
                "icons": [
                    {
                        "id": "test-icon",
                        "display_name": "Test Icon",
                        "aliases": [],
                        "category": "providers",
                        "codepoint": "U+100000",
                        "asset_status": "reserved",
                    }
                ],
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "available glyph assets"):
                patch_font_branch(
                    source_path,
                    root / "out",
                    manifest,
                    use_placeholder_glyphs=True,
                )


def _available_icon_manifest(
    codepoint: str = "U+100000",
    range_start: str = "U+100000",
    range_end: str = "U+1000FF",
) -> Manifest:
    return parse_manifest(
        _available_icon_manifest_raw(
            codepoint=codepoint,
            range_start=range_start,
            range_end=range_end,
        )
    )


def _available_icon_manifest_json() -> str:
    return json.dumps(_available_icon_manifest_raw())


def _available_icon_manifest_raw(
    codepoint: str = "U+100000",
    range_start: str = "U+100000",
    range_end: str = "U+1000FF",
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "manifest_version": "test",
        "project": "agent-font-patcher",
        "range": {
            "start": range_start,
            "end": range_end,
            "description": "test",
        },
        "blocks": [
            {
                "name": "providers",
                "start": range_start,
                "end": range_end,
                "description": "test",
            }
        ],
        "icons": [
            {
                "id": "test-icon",
                "display_name": "Test Icon",
                "aliases": [],
                "category": "providers",
                "codepoint": codepoint,
                "asset_status": "available",
                "source": "agent-font-patcher-test",
                "license": "test-fixture",
                "attribution": "agent-font-patcher",
            }
        ],
    }
