from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from agent_font_patcher.font_cache import FontCacheError, refresh_font_cache


class FontCacheTest(unittest.TestCase):
    def test_refresh_macos_user_cache_runs_atsutil_sequence(self) -> None:
        commands: list[list[str]] = []

        result = refresh_font_cache(
            platform_name="darwin",
            runner=commands.append,
            which=lambda name: f"/usr/bin/{name}" if name == "atsutil" else None,
        )

        self.assertEqual(
            commands,
            [
                ["atsutil", "databases", "-removeUser"],
                ["atsutil", "server", "-shutdown"],
                ["atsutil", "server", "-ping"],
            ],
        )
        self.assertEqual(result.platform, "darwin")
        self.assertEqual(result.scope, "user")
        self.assertIn("Restart affected terminal apps", result.restart_hint)

    def test_refresh_macos_rejects_system_scope(self) -> None:
        with self.assertRaisesRegex(FontCacheError, "system"):
            refresh_font_cache(
                platform_name="darwin",
                scope="system",
                runner=lambda command: None,
                which=lambda name: f"/usr/bin/{name}",
            )

    def test_refresh_macos_requires_atsutil(self) -> None:
        with self.assertRaisesRegex(FontCacheError, "atsutil"):
            refresh_font_cache(
                platform_name="darwin",
                runner=lambda command: None,
                which=lambda name: None,
            )

    def test_refresh_linux_cache_scopes_existing_font_dirs(self) -> None:
        commands: list[list[str]] = []

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            font_dir = root / "fonts"
            font_dir.mkdir()

            result = refresh_font_cache(
                platform_name="linux",
                font_dirs=(font_dir, font_dir),
                runner=commands.append,
                which=lambda name: "/usr/bin/fc-cache" if name == "fc-cache" else None,
            )

        self.assertEqual(commands, [["fc-cache", "-f", str(font_dir.resolve())]])
        self.assertEqual(result.commands, (("fc-cache", "-f", str(font_dir.resolve())),))

    def test_refresh_linux_system_cache_does_not_scope_dirs(self) -> None:
        commands: list[list[str]] = []

        result = refresh_font_cache(
            platform_name="linux",
            scope="system",
            runner=commands.append,
            which=lambda name: "/usr/bin/fc-cache" if name == "fc-cache" else None,
        )

        self.assertEqual(commands, [["fc-cache", "-f", "-s"]])
        self.assertEqual(result.scope, "system")

    def test_refresh_rejects_font_dirs_with_system_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            font_dir = Path(tmp) / "fonts"
            font_dir.mkdir()

            with self.assertRaisesRegex(FontCacheError, "font-dir"):
                refresh_font_cache(
                    platform_name="linux",
                    scope="system",
                    font_dirs=(font_dir,),
                    runner=lambda command: None,
                    which=lambda name: "/usr/bin/fc-cache" if name == "fc-cache" else None,
                )

    def test_refresh_linux_requires_fc_cache(self) -> None:
        with self.assertRaisesRegex(FontCacheError, "fc-cache"):
            refresh_font_cache(
                platform_name="linux",
                runner=lambda command: None,
                which=lambda name: None,
            )

    def test_refresh_linux_rejects_invalid_explicit_font_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing_dir = Path(tmp) / "missing"

            with self.assertRaisesRegex(FontCacheError, "font directory"):
                refresh_font_cache(
                    platform_name="linux",
                    font_dirs=(missing_dir,),
                    runner=lambda command: None,
                    which=lambda name: "/usr/bin/fc-cache" if name == "fc-cache" else None,
                )

    def test_refresh_windows_reports_manual_restart_hint(self) -> None:
        result = refresh_font_cache(
            platform_name="win32",
            runner=lambda command: None,
            which=lambda name: None,
        )

        self.assertEqual(result.commands, ())
        self.assertIn("No automatic Windows", result.restart_hint)

    def test_refresh_windows_rejects_system_scope(self) -> None:
        with self.assertRaisesRegex(FontCacheError, "system"):
            refresh_font_cache(
                platform_name="win32",
                scope="system",
                runner=lambda command: None,
                which=lambda name: None,
            )

    def test_refresh_wraps_command_failures(self) -> None:
        def failing_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
            raise subprocess.CalledProcessError(1, command)

        with self.assertRaisesRegex(FontCacheError, "failed"):
            refresh_font_cache(
                platform_name="linux",
                runner=failing_runner,
                which=lambda name: "/usr/bin/fc-cache" if name == "fc-cache" else None,
            )


if __name__ == "__main__":
    unittest.main()
