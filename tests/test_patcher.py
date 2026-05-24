from __future__ import annotations

import contextlib
import io
import json
import os
import stat
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fontTools.ttLib import TTCollection, TTFont
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable

from agent_font_patcher.cli import (
    build_parser,
    handle_cache_refresh,
    handle_inspect,
    handle_patch,
    handle_preview,
    handle_restore,
)
from agent_font_patcher.font_cache import FontCacheError, FontCacheRefreshResult
from agent_font_patcher.inspector import inspect_agent_font
from agent_font_patcher.manifest import Manifest, parse_manifest
from agent_font_patcher.patcher import (
    PatchError,
    _best_unicode_cmap,
    patch_font_branch,
    patch_font_in_place,
    read_patch_metadata,
    restore_font_backup,
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
                        in_place=False,
                        backup_dir=None,
                        no_backup=False,
                        refresh_cache=False,
                        no_refresh_cache=False,
                    )
                )

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn(f"source: {source_path}", output)
        self.assertIn(f"output: {output_dir / 'ExampleNerdFont-Regular-Agent.ttf'}", output)
        self.assertIn("placeholder_glyphs: yes", output)
        self.assertIn("patched_codepoints: 1", output)

    def test_patch_font_in_place_preserves_names_and_creates_backup(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            original_bytes = source_path.read_bytes()

            result = patch_font_in_place(
                source_path,
                manifest,
                use_placeholder_glyphs=True,
            )
            candidate = inspect_font(source_path)
            codepoints = read_font_codepoints(source_path)
            metadata = read_patch_metadata(source_path)
            backup_bytes = result.backup_path.read_bytes() if result.backup_path else None

        self.assertEqual(result.output_path, source_path)
        self.assertEqual(result.backup_path, source_path.with_name(f"{source_path.name}.agent-font-patcher-backup"))
        self.assertEqual(backup_bytes, original_bytes)
        self.assertEqual(candidate.family, "Example Nerd Font")
        self.assertEqual(candidate.full_name, "Example Nerd Font Regular")
        self.assertIn(0x100000, codepoints.codepoints)
        self.assertIsNotNone(metadata)
        self.assertEqual(metadata["source_font_name"], "Example Nerd Font Regular")

    def test_patch_font_in_place_can_skip_backup(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            result = patch_font_in_place(
                source_path,
                manifest,
                use_placeholder_glyphs=True,
                create_backup=False,
            )
            backup_exists = source_path.with_name(f"{source_path.name}.agent-font-patcher-backup").exists()

        self.assertIsNone(result.backup_path)
        self.assertFalse(backup_exists)

    def test_patch_font_in_place_uses_backup_dir(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backup_dir = root / "backups"
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            original_bytes = source_path.read_bytes()

            result = patch_font_in_place(
                source_path,
                manifest,
                use_placeholder_glyphs=True,
                backup_dir=backup_dir,
            )
            backup_bytes = result.backup_path.read_bytes() if result.backup_path else None

        self.assertEqual(result.backup_path, backup_dir / f"{source_path.name}.agent-font-patcher-backup")
        self.assertEqual(backup_bytes, original_bytes)

    def test_patch_font_in_place_preserves_source_mode(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            source_path.chmod(0o644)

            patch_font_in_place(
                source_path,
                manifest,
                use_placeholder_glyphs=True,
                create_backup=False,
            )
            patched_mode = stat.S_IMODE(source_path.stat().st_mode)

        self.assertEqual(patched_mode, 0o644)

    def test_patch_font_in_place_preserves_source_owner_when_permitted(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            source_stat = source_path.stat()

            with mock.patch("agent_font_patcher.patcher.os.chown") as chown:
                patch_font_in_place(
                    source_path,
                    manifest,
                    use_placeholder_glyphs=True,
                    create_backup=False,
                )

        self.assertTrue(
            any(call.args[1:] == (source_stat.st_uid, source_stat.st_gid) for call in chown.call_args_list)
        )

    def test_patch_font_in_place_fails_when_source_owner_cannot_be_preserved(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            source_stat = source_path.stat()
            mismatched_stat = mock.Mock(st_uid=source_stat.st_uid + 1, st_gid=source_stat.st_gid)

            def fake_stat(path: Path, *args: object, **kwargs: object) -> object:
                if path == source_path:
                    return source_stat
                if path.name.startswith(f".{source_path.name}."):
                    return mismatched_stat
                return original_stat(path, *args, **kwargs)

            original_stat = Path.stat
            with (
                mock.patch("agent_font_patcher.patcher.os.chown", side_effect=PermissionError("denied")),
                mock.patch.object(Path, "stat", autospec=True, side_effect=fake_stat),
                self.assertRaisesRegex(PatchError, "unable to patch font"),
            ):
                patch_font_in_place(
                    source_path,
                    manifest,
                    use_placeholder_glyphs=True,
                    create_backup=False,
                )

    def test_patch_font_in_place_ignores_chown_denial_when_owner_already_matches(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            source_stat = source_path.stat()

            with (
                mock.patch("agent_font_patcher.patcher.os.chown", side_effect=PermissionError("denied")),
                mock.patch.object(Path, "stat", autospec=True, return_value=source_stat),
            ):
                result = patch_font_in_place(
                    source_path,
                    manifest,
                    use_placeholder_glyphs=True,
                    create_backup=False,
                )

        self.assertEqual(result.output_path, source_path)

    def test_patch_font_in_place_allows_platforms_without_chown(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with mock.patch("agent_font_patcher.patcher.os.chown", new=None):
                result = patch_font_in_place(
                    source_path,
                    manifest,
                    use_placeholder_glyphs=True,
                    create_backup=False,
                )

        self.assertEqual(result.output_path, source_path)

    def test_patch_font_in_place_requires_writable_font_directory_before_backup(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            backup_dir = root / "backups"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            def fake_access(path: Path, mode: int) -> bool:
                if mode == os.W_OK and path == source_path.parent:
                    return False
                return True

            with (
                mock.patch("agent_font_patcher.patcher.os.access", side_effect=fake_access),
                self.assertRaisesRegex(PatchError, "font directory is not writable"),
            ):
                patch_font_in_place(
                    source_path,
                    manifest,
                    use_placeholder_glyphs=True,
                    backup_dir=backup_dir,
                )

        self.assertFalse(backup_dir.exists())

    def test_patch_font_in_place_refuses_existing_backup(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            backup_path = source_path.with_name(f"{source_path.name}.agent-font-patcher-backup")
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            backup_path.write_bytes(b"existing")

            with self.assertRaisesRegex(PatchError, "backup already exists"):
                patch_font_in_place(
                    source_path,
                    manifest,
                    use_placeholder_glyphs=True,
                )

    def test_patch_font_in_place_rejects_dangling_symlink_before_open(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            source_path.symlink_to(root / "missing.ttf")

            with self.assertRaisesRegex(PatchError, "symlinked"):
                patch_font_in_place(
                    source_path,
                    manifest,
                    use_placeholder_glyphs=True,
                )

    def test_patch_font_in_place_removes_backup_when_replace_fails(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            backup_path = source_path.with_name(f"{source_path.name}.agent-font-patcher-backup")
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            original_bytes = source_path.read_bytes()

            with (
                mock.patch("agent_font_patcher.patcher._save_font_replace", side_effect=OSError("boom")),
                self.assertRaisesRegex(PatchError, "unable to patch font"),
            ):
                patch_font_in_place(
                    source_path,
                    manifest,
                    use_placeholder_glyphs=True,
                )

            self.assertFalse(backup_path.exists())
            self.assertEqual(source_path.read_bytes(), original_bytes)

    def test_restore_font_backup_restores_original_font(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            original_bytes = source_path.read_bytes()
            patch_font_in_place(
                source_path,
                manifest,
                use_placeholder_glyphs=True,
            )

            backup_path = restore_font_backup(source_path)
            restored_bytes = source_path.read_bytes()
            codepoints = read_font_codepoints(source_path)

        self.assertEqual(backup_path, source_path.with_name(f"{source_path.name}.agent-font-patcher-backup"))
        self.assertEqual(restored_bytes, original_bytes)
        self.assertNotIn(0x100000, codepoints.codepoints)

    def test_restore_font_backup_wraps_io_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            backup_path = source_path.with_name(f"{source_path.name}.agent-font-patcher-backup")
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            backup_path.mkdir()

            with self.assertRaisesRegex(PatchError, "unable to restore font"):
                restore_font_backup(source_path)

    def test_restore_command_prints_restored_path(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            patch_font_in_place(
                source_path,
                manifest,
                use_placeholder_glyphs=True,
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = handle_restore(SimpleNamespace(font_path=source_path, backup_dir=None))

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn(f"restored: {source_path}", output)
        self.assertIn("backup:", output)

    def test_patch_command_can_patch_in_place(self) -> None:
        manifest_path_content = _available_icon_manifest_json()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
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
                        output_dir=None,
                        manifest_path=manifest_path,
                        use_placeholder_glyphs=True,
                        in_place=True,
                        backup_dir=None,
                        no_backup=False,
                        refresh_cache=False,
                        no_refresh_cache=True,
                    )
                )

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn(f"output: {source_path}", output)
        self.assertIn("backup:", output)
        self.assertIn("patched_codepoints: 1", output)

    def test_patch_command_refreshes_cache_by_default_for_in_place_mode(self) -> None:
        manifest_path_content = _available_icon_manifest_json()
        cache_result = FontCacheRefreshResult(
            platform="test",
            scope="user",
            commands=(("cache-tool", "refresh"),),
            restart_hint="restart apps",
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            manifest_path = root / "manifest.json"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            manifest_path.write_text(manifest_path_content, encoding="utf-8")

            stdout = io.StringIO()
            with (
                mock.patch("agent_font_patcher.cli.refresh_font_cache", return_value=cache_result) as refresh,
                contextlib.redirect_stdout(stdout),
            ):
                exit_code = handle_patch(
                    SimpleNamespace(
                        font_path=source_path,
                        output_dir=None,
                        manifest_path=manifest_path,
                        use_placeholder_glyphs=True,
                        in_place=True,
                        backup_dir=None,
                        no_backup=False,
                        refresh_cache=False,
                        no_refresh_cache=False,
                    )
                )

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        refresh.assert_called_once_with(font_dirs=(source_path.parent,))
        self.assertIn("cache_refresh: test user", output)
        self.assertIn("cache-tool refresh", output)

    def test_patch_command_can_skip_cache_refresh(self) -> None:
        manifest_path_content = _available_icon_manifest_json()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            manifest_path = root / "manifest.json"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            manifest_path.write_text(manifest_path_content, encoding="utf-8")

            with mock.patch("agent_font_patcher.cli.refresh_font_cache") as refresh:
                handle_patch(
                    SimpleNamespace(
                        font_path=source_path,
                        output_dir=None,
                        manifest_path=manifest_path,
                        use_placeholder_glyphs=True,
                        in_place=True,
                        backup_dir=None,
                        no_backup=False,
                        refresh_cache=False,
                        no_refresh_cache=True,
                    )
                )

        refresh.assert_not_called()

    def test_patch_command_prints_patch_result_before_cache_refresh_failure(self) -> None:
        manifest_path_content = _available_icon_manifest_json()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            manifest_path = root / "manifest.json"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            manifest_path.write_text(manifest_path_content, encoding="utf-8")

            stdout = io.StringIO()
            with (
                mock.patch(
                    "agent_font_patcher.cli.refresh_font_cache",
                    side_effect=FontCacheError("cache failed"),
                ),
                contextlib.redirect_stdout(stdout),
                self.assertRaisesRegex(FontCacheError, "cache failed"),
            ):
                handle_patch(
                    SimpleNamespace(
                        font_path=source_path,
                        output_dir=None,
                        manifest_path=manifest_path,
                        use_placeholder_glyphs=True,
                        in_place=True,
                        backup_dir=None,
                        no_backup=False,
                        refresh_cache=False,
                        no_refresh_cache=False,
                    )
                )

        output = stdout.getvalue()
        self.assertIn(f"output: {source_path}", output)
        self.assertIn("patched_codepoints: 1", output)

    def test_patch_command_requires_output_dir_for_branch_mode(self) -> None:
        manifest_path_content = _available_icon_manifest_json()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            manifest_path = root / "manifest.json"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            manifest_path.write_text(manifest_path_content, encoding="utf-8")

            with self.assertRaisesRegex(PatchError, "output-dir"):
                handle_patch(
                    SimpleNamespace(
                        font_path=source_path,
                        output_dir=None,
                        manifest_path=manifest_path,
                        use_placeholder_glyphs=True,
                        in_place=False,
                        backup_dir=None,
                        no_backup=False,
                        refresh_cache=False,
                        no_refresh_cache=False,
                    )
                )

    def test_patch_command_validates_flags_before_manifest_loading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with mock.patch("agent_font_patcher.cli.load_manifest") as load_manifest_mock:
                with self.assertRaisesRegex(PatchError, "output-dir"):
                    handle_patch(
                        SimpleNamespace(
                            font_path=root / "ExampleNerdFont-Regular.ttf",
                            output_dir=None,
                            manifest_path=root / "missing.json",
                            use_placeholder_glyphs=True,
                            in_place=False,
                            backup_dir=None,
                            no_backup=False,
                            refresh_cache=False,
                            no_refresh_cache=False,
                        )
                    )

        load_manifest_mock.assert_not_called()

    def test_patch_command_rejects_output_dir_for_in_place_mode(self) -> None:
        manifest_path_content = _available_icon_manifest_json()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            manifest_path = root / "manifest.json"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            manifest_path.write_text(manifest_path_content, encoding="utf-8")

            with self.assertRaisesRegex(PatchError, "output-dir"):
                handle_patch(
                    SimpleNamespace(
                        font_path=source_path,
                        output_dir=root / "out",
                        manifest_path=manifest_path,
                        use_placeholder_glyphs=True,
                        in_place=True,
                        backup_dir=None,
                        no_backup=False,
                        refresh_cache=False,
                        no_refresh_cache=False,
                    )
                )

    def test_patch_command_rejects_backup_dir_with_no_backup(self) -> None:
        manifest_path_content = _available_icon_manifest_json()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            manifest_path = root / "manifest.json"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            manifest_path.write_text(manifest_path_content, encoding="utf-8")

            with self.assertRaisesRegex(PatchError, "backup-dir"):
                handle_patch(
                    SimpleNamespace(
                        font_path=source_path,
                        output_dir=None,
                        manifest_path=manifest_path,
                        use_placeholder_glyphs=True,
                        in_place=True,
                        backup_dir=root / "backups",
                        no_backup=True,
                        refresh_cache=False,
                        no_refresh_cache=False,
                    )
                )

    def test_patch_command_rejects_conflicting_cache_refresh_flags(self) -> None:
        manifest_path_content = _available_icon_manifest_json()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            manifest_path = root / "manifest.json"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )
            manifest_path.write_text(manifest_path_content, encoding="utf-8")

            with self.assertRaisesRegex(PatchError, "refresh-cache"):
                handle_patch(
                    SimpleNamespace(
                        font_path=source_path,
                        output_dir=None,
                        manifest_path=manifest_path,
                        use_placeholder_glyphs=True,
                        in_place=True,
                        backup_dir=None,
                        no_backup=False,
                        refresh_cache=True,
                        no_refresh_cache=True,
                    )
                )

    def test_cache_refresh_command_prints_result(self) -> None:
        cache_result = FontCacheRefreshResult(
            platform="test",
            scope="user",
            commands=(("cache-tool", "refresh"),),
            restart_hint="restart apps",
        )

        stdout = io.StringIO()
        with (
            mock.patch("agent_font_patcher.cli.refresh_font_cache", return_value=cache_result) as refresh,
            contextlib.redirect_stdout(stdout),
        ):
            exit_code = handle_cache_refresh(
                SimpleNamespace(system=False, user=True, font_dir=[Path("/fonts")])
            )

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        refresh.assert_called_once_with(scope="user", font_dirs=(Path("/fonts"),))
        self.assertIn("cache_refresh: test user", output)
        self.assertIn("cache-tool refresh", output)

    def test_cache_command_requires_subcommand(self) -> None:
        parser = build_parser()

        with self.assertRaises(SystemExit) as error:
            parser.parse_args(["cache"])

        self.assertNotEqual(error.exception.code, 0)

    def test_preview_command_writes_specimen(self) -> None:
        manifest_path_content = _available_icon_manifest_json()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            font_path = root / "ExampleNerdFont-Regular.ttf"
            manifest_path = root / "manifest.json"
            output_path = root / "preview.html"
            _write_minimal_font(
                font_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
                extra_codepoints={0x100000: "agent.test_icon"},
            )
            manifest_path.write_text(manifest_path_content, encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = handle_preview(
                    SimpleNamespace(
                        font_path=font_path,
                        manifest_path=manifest_path,
                        output=output_path,
                        output_dir=None,
                    )
                )
            html = output_path.read_text(encoding="utf-8")

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn(f"output: {output_path}", output)
        self.assertIn("agent_glyphs: 1/1 present", output)
        self.assertIn("Test Icon", html)

    def test_preview_command_rejects_output_and_output_dir(self) -> None:
        with self.assertRaisesRegex(ValueError, "output"):
            handle_preview(
                SimpleNamespace(
                    font_path=Path("Example.ttf"),
                    manifest_path=None,
                    output=Path("preview.html"),
                    output_dir=Path("out"),
                )
            )

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

    def test_patch_font_branch_reports_missing_svg_asset(self) -> None:
        manifest = _available_icon_manifest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "unable to read SVG asset"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_ingests_svg_path_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                '<svg viewBox="0 0 24 24"><path d="M 12 2 L 22 22 L 2 22 Z"/></svg>',
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            result = patch_font_branch(source_path, root / "out", manifest)
            codepoints = read_font_codepoints(result.output_path)
            font = TTFont(result.output_path)
            glyph = font["glyf"]["agent.test_icon"]
            advance_width, left_side_bearing = font["hmtx"].metrics["agent.test_icon"]
            bounds = glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax
            font.close()

        self.assertIn(0x100000, codepoints.codepoints)
        self.assertGreater(glyph.numberOfContours, 0)
        self.assertEqual(advance_width, 500)
        self.assertEqual(bounds, (42, 292, 458, 708))
        self.assertEqual(left_side_bearing, 42)

    def test_patch_font_branch_resolves_svg_assets_relative_to_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_dir = root / "manifest"
            manifest_dir.mkdir()
            svg_path = manifest_dir / "icon.svg"
            svg_path.write_text(
                '<svg viewBox="0 0 24 24"><path d="M 12 2 L 22 22 L 2 22 Z"/></svg>',
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source="icon.svg")
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
                asset_base_dir=manifest_dir,
            )
            codepoints = read_font_codepoints(result.output_path)

        self.assertIn(0x100000, codepoints.codepoints)

    def test_patch_font_branch_requires_svg_path_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text('<svg viewBox="0 0 1000 1000"></svg>', encoding="utf-8")
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "path data"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_wraps_malformed_svg_path_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                '<svg viewBox="0 0 24 24"><path d="M 0"/></svg>',
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "SVG path data"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_unparsed_svg_path_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                '<svg viewBox="0 0 24 24"><path d="M 0 0 L 10 10 @"/></svg>',
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "SVG path data"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_malformed_svg_path_separators(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                '<svg viewBox="0 0 24 24"><path d="M 1,,1 L 20 1 L 20 20 Z"/></svg>',
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "malformed separator"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_trailing_svg_path_commas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                '<svg viewBox="0 0 24 24"><path d="M 1 1 L 20 1 L 20 20 Z,"/></svg>',
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "malformed separator"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_fonttools_incompatible_number_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                '<svg viewBox="0 0 24 24"><path d="M 1 1 H 1.e2 V 20 Z"/></svg>',
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "SVG path data"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_svg_curve_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                '<svg viewBox="0 0 24 24"><path d="M 1 1 C 2 2 3 3 4 4"/></svg>',
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "SVG path data"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_svg_dangling_exponent_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                '<svg viewBox="0 0 24 24"><path d="M 0 0 L 10 10 e"/></svg>',
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "SVG path data"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_empty_svg_glyphs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text('<svg viewBox="0 0 24 24"><path d="M 0 0"/></svg>', encoding="utf-8")
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "empty glyph"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_zero_area_svg_glyphs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                '<svg viewBox="0 0 24 24"><path d="M 0 0 L 10 0 Z"/></svg>',
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "empty glyph"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_collinear_zero_area_svg_glyphs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                '<svg viewBox="0 0 24 24"><path d="M 0 0 L 10 10 L 20 20 Z"/></svg>',
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "empty glyph"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_mixed_degenerate_svg_contours(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                (
                    '<svg viewBox="0 0 24 24">'
                    '<path d="M 1 1 L 20 1 L 20 20 Z M 0 0 L 10 0 Z"/>'
                    "</svg>"
                ),
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "empty glyph"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_dropped_zero_area_svg_subpaths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                (
                    '<svg viewBox="0 0 24 24">'
                    '<path d="M 1 1 L 20 1 L 20 20 Z M 0 0 Z"/>'
                    "</svg>"
                ),
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "empty glyph"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_separator_only_svg_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text('<svg viewBox="0 0 24 24"><path d="   "/></svg>', encoding="utf-8")
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "path data"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_non_finite_svg_path_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                '<svg viewBox="0 0 24 24"><path d="M 1e309 0 L 2 2 Z"/></svg>',
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "SVG path data"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_out_of_range_svg_path_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                '<svg viewBox="0 0 24 24"><path d="M 100000 0 L 2 2 Z"/></svg>',
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "out-of-range"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_out_of_range_raw_svg_path_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                (
                    '<svg viewBox="0 0 32767 32767">'
                    '<path d="M 40000 0 L 40001 0 L 40001 1 Z"/>'
                    "</svg>"
                ),
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "out-of-range coordinate"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_out_of_range_svg_viewbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                '<svg viewBox="0 0 1000000 1000000"><path d="M 1 1 L 2 1 L 2 2 Z"/></svg>',
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "invalid viewBox"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_out_of_cell_svg_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                '<svg viewBox="0 0 24 24"><path d="M 100 0 L 110 0 L 110 10 Z"/></svg>',
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "out-of-cell"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_accepts_svg_exponent_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                '<svg viewBox="0 0 24 24"><path d="M 1e0 1e0 L 2e1 1e0 L 2e1 2e1 Z"/></svg>',
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            result = patch_font_branch(source_path, root / "out", manifest)
            codepoints = read_font_codepoints(result.output_path)

        self.assertIn(0x100000, codepoints.codepoints)

    def test_patch_font_branch_accepts_svg_moveto_implicit_line_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                '<svg viewBox="0 0 24 24"><path d="M 1 1 20 1 20 20 Z"/></svg>',
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            result = patch_font_branch(source_path, root / "out", manifest)
            codepoints = read_font_codepoints(result.output_path)

        self.assertIn(0x100000, codepoints.codepoints)

    def test_patch_font_branch_parses_multiple_svg_paths_independently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                (
                    '<svg viewBox="0 0 24 24">'
                    '<path d="M 20 20 l 1 0 l 0 1 z"/>'
                    '<path d="m 1 1 l 1 0 l 0 1 z"/>'
                    "</svg>"
                ),
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            result = patch_font_branch(source_path, root / "out", manifest)
            font = TTFont(result.output_path)
            glyph = font["glyf"]["agent.test_icon"]
            bounds = glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax
            font.close()

        self.assertEqual(bounds, (21, 313, 438, 729))

    def test_patch_font_branch_wraps_svg_parser_attribute_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text('<svg viewBox="0 0 24 24"><path d="Z"/></svg>', encoding="utf-8")
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "SVG path data"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_wraps_svg_pen_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                '<svg viewBox="0 0 24 24"><path d="M0 0L1 0L1 1Z L2 2"/></svg>',
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "SVG path data"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_non_finite_viewbox_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                '<svg viewBox="0 0 NaN 24"><path d="M 12 2 L 22 22 L 2 22 Z"/></svg>',
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "invalid viewBox"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_malformed_viewbox_separators(self) -> None:
        for viewbox in ("0,,0 24 24", ",0 0 24 24", "0 0 24 24,"):
            with self.subTest(viewbox=viewbox):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    svg_path = root / "icon.svg"
                    svg_path.write_text(
                        (
                            f'<svg viewBox="{viewbox}">'
                            '<path d="M 12 2 L 22 22 L 2 22 Z"/>'
                            "</svg>"
                        ),
                        encoding="utf-8",
                    )
                    manifest = _available_icon_manifest(source=str(svg_path))
                    source_path = root / "ExampleNerdFont-Regular.ttf"
                    _write_minimal_font(
                        source_path,
                        family="Example Nerd Font",
                        full_name="Example Nerd Font Regular",
                    )

                    with self.assertRaisesRegex(PatchError, "invalid viewBox"):
                        patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_malformed_viewbox_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                '<svg viewBox="0 0 1_000 1_000"><path d="M 12 2 L 22 22 L 2 22 Z"/></svg>',
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "invalid viewBox"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_svg_entities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                (
                    '<!DOCTYPE svg [<!ENTITY iconPath "M 12 2 L 22 22 L 2 22 Z">]>'
                    '<svg viewBox="0 0 24 24"><path d="&iconPath;"/></svg>'
                ),
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "unsupported XML constructs"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_numeric_svg_entities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                '<svg viewBox="0 0 24 24"><path d="M &#49; 1 L 2 1 L 2 2 Z"/></svg>',
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "unsupported XML constructs"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_xml_stylesheet_processing_instructions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                (
                    '<?xml version="1.0"?>'
                    '<?xml-stylesheet href="style.css" type="text/css"?>'
                    '<svg viewBox="0 0 24 24"><path d="M 12 2 L 22 22 L 2 22 Z"/></svg>'
                ),
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "unsupported XML constructs"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_leading_xml_stylesheet_processing_instructions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                (
                    '<?xml-stylesheet href="style.css" type="text/css"?>'
                    '<svg viewBox="0 0 24 24"><path d="M 12 2 L 22 22 L 2 22 Z"/></svg>'
                ),
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "unsupported XML constructs"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_non_ascii_processing_instructions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                '<?é test?><svg viewBox="0 0 24 24"><path d="M 12 2 L 22 22 L 2 22 Z"/></svg>',
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "unsupported XML constructs"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_encoded_xml_stylesheet_processing_instructions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_bytes(
                (
                    '<?xml version="1.0" encoding="UTF-16"?>'
                    '<?xml-stylesheet href="style.css" type="text/css"?>'
                    '<svg viewBox="0 0 24 24"><path d="M 12 2 L 22 22 L 2 22 Z"/></svg>'
                ).encode("utf-16")
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "UTF-8"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_accepts_xml_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                '<?xml version="1.0"?><svg viewBox="0 0 24 24"><path d="M 12 2 L 22 22 L 2 22 Z"/></svg>',
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            result = patch_font_branch(source_path, root / "out", manifest)
            codepoints = read_font_codepoints(result.output_path)

        self.assertIn(0x100000, codepoints.codepoints)

    def test_patch_font_branch_accepts_xml_declaration_with_utf8_encoding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                (
                    '<?xml version="1.0" encoding="UTF-8" standalone="no"?>'
                    '<svg viewBox="0 0 24 24"><path d="M 12 2 L 22 22 L 2 22 Z"/></svg>'
                ),
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            result = patch_font_branch(source_path, root / "out", manifest)
            codepoints = read_font_codepoints(result.output_path)

        self.assertIn(0x100000, codepoints.codepoints)

    def test_patch_font_branch_rejects_invalid_xml_declarations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                (
                    '<?xml version="2.0"?>'
                    '<svg viewBox="0 0 24 24"><path d="M 12 2 L 22 22 L 2 22 Z"/></svg>'
                ),
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "unsupported XML constructs"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_non_whitespace_svg_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                (
                    '<svg viewBox="0 0 24 24">'
                    "ignored"
                    '<path d="M 12 2 L 22 22 L 2 22 Z"/>'
                    "</svg>"
                ),
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "unsupported text content"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_non_whitespace_svg_tail_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                (
                    '<svg viewBox="0 0 24 24">'
                    '<path d="M 12 2 L 22 22 L 2 22 Z"/>'
                    "ignored"
                    "</svg>"
                ),
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "unsupported text content"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_accepts_svg_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                (
                    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
                    '<path d="M 12 2 L 22 22 L 2 22 Z"/>'
                    "</svg>"
                ),
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            result = patch_font_branch(source_path, root / "out", manifest)
            codepoints = read_font_codepoints(result.output_path)

        self.assertIn(0x100000, codepoints.codepoints)

    def test_patch_font_branch_rejects_foreign_svg_namespaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                (
                    '<svg xmlns="urn:not-svg" viewBox="0 0 24 24">'
                    '<path d="M 12 2 L 22 22 L 2 22 Z"/>'
                    "</svg>"
                ),
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "unsupported XML constructs"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_foreign_namespaced_svg_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                (
                    '<svg xmlns:foreign="urn:not-svg" viewBox="0 0 24 24">'
                    '<foreign:path d="M 12 2 L 22 22 L 2 22 Z"/>'
                    "</svg>"
                ),
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "unsupported XML constructs"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_unused_foreign_namespace_declarations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                (
                    '<svg xmlns:foreign="urn:not-svg" viewBox="0 0 24 24">'
                    '<path d="M 12 2 L 22 22 L 2 22 Z"/>'
                    "</svg>"
                ),
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "unsupported XML constructs"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_svg_comments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                '<svg viewBox="0 0 24 24"><!-- hidden --><path d="M 12 2 L 22 22 L 2 22 Z"/></svg>',
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "unsupported XML constructs"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_svg_cdata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                (
                    '<svg viewBox="0 0 24 24">'
                    '<path d="M 12 2 L 22 22 L 2 22 Z"/>'
                    "<![CDATA[ignored]]>"
                    "</svg>"
                ),
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "unsupported XML constructs"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_svg_transforms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                (
                    '<svg viewBox="0 0 24 24">'
                    '<g transform="translate(12 0)"><path d="M 1 1 L 2 1 L 2 2 Z"/></g>'
                    "</svg>"
                ),
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "unsupported transforms"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_svg_style_transforms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                (
                    '<svg viewBox="0 0 24 24">'
                    '<path style="transform: translate(12px, 0)" d="M 1 1 L 2 1 L 2 2 Z"/>'
                    "</svg>"
                ),
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "unsupported transforms"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_svg_style_attributes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                (
                    '<svg viewBox="0 0 24 24">'
                    '<path style="display:none" d="M 1 1 L 2 1 L 2 2 Z"/>'
                    "</svg>"
                ),
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "unsupported style"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_unsupported_svg_drawing_elements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                (
                    '<svg viewBox="0 0 24 24">'
                    '<path d="M 1 1 L 2 1 L 2 2 Z"/>'
                    '<circle cx="12" cy="12" r="3"/>'
                    "</svg>"
                ),
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "unsupported elements"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_unsupported_svg_script_elements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                (
                    '<svg viewBox="0 0 24 24">'
                    "<script>alert(1)</script>"
                    '<path d="M 1 1 L 2 1 L 2 2 Z"/>'
                    "</svg>"
                ),
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "unsupported elements"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_non_svg_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                '<g viewBox="0 0 24 24"><path d="M 1 1 L 2 1 L 2 2 Z"/></g>',
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "unsupported elements"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_nested_svg_viewports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                (
                    '<svg viewBox="0 0 24 24">'
                    '<svg viewBox="0 0 240 240">'
                    '<path d="M 12 2 L 22 22 L 2 22 Z"/>'
                    "</svg>"
                    "</svg>"
                ),
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "unsupported elements"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_path_child_elements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                (
                    '<svg viewBox="0 0 24 24">'
                    '<path d="M 1 1 L 20 1 L 20 20 Z">'
                    '<path d="M 2 2 L 3 2 L 3 3 Z"/>'
                    "</path>"
                    "</svg>"
                ),
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "unsupported elements"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_unsupported_path_presentation_attributes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                (
                    '<svg viewBox="0 0 24 24">'
                    '<path fill="none" stroke="black" d="M 1 1 L 2 1 L 2 2 Z"/>'
                    "</svg>"
                ),
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "unsupported attributes"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_inherited_svg_presentation_attributes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                (
                    '<svg viewBox="0 0 24 24">'
                    '<g fill="none" stroke="black">'
                    '<path d="M 1 1 L 2 1 L 2 2 Z"/>'
                    "</g>"
                    "</svg>"
                ),
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "unsupported attributes"):
                patch_font_branch(source_path, root / "out", manifest)

    def test_patch_font_branch_rejects_svg_defs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            svg_path = root / "icon.svg"
            svg_path.write_text(
                (
                    '<svg viewBox="0 0 24 24">'
                    '<defs><path id="shape" d="M 1 1 L 2 1 L 2 2 Z"/></defs>'
                    "</svg>"
                ),
                encoding="utf-8",
            )
            manifest = _available_icon_manifest(source=str(svg_path))
            source_path = root / "ExampleNerdFont-Regular.ttf"
            _write_minimal_font(
                source_path,
                family="Example Nerd Font",
                full_name="Example Nerd Font Regular",
            )

            with self.assertRaisesRegex(PatchError, "unsupported elements"):
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
    source: str = "agent-font-patcher-test",
) -> Manifest:
    return parse_manifest(
        _available_icon_manifest_raw(
            codepoint=codepoint,
            range_start=range_start,
            range_end=range_end,
            source=source,
        )
    )


def _available_icon_manifest_json() -> str:
    return json.dumps(_available_icon_manifest_raw())


def _available_icon_manifest_raw(
    codepoint: str = "U+100000",
    range_start: str = "U+100000",
    range_end: str = "U+1000FF",
    source: str = "agent-font-patcher-test",
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
                "source": source,
                "license": "test-fixture",
                "attribution": "agent-font-patcher",
            }
        ],
    }
