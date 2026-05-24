from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


class FontCacheError(ValueError):
    """Raised when font cache refresh cannot be completed."""


class CommandRunner(Protocol):
    def __call__(self, command: list[str]) -> subprocess.CompletedProcess[str]: ...


@dataclass(frozen=True)
class FontCacheRefreshResult:
    platform: str
    scope: str
    commands: tuple[tuple[str, ...], ...]
    restart_hint: str


TERMINAL_RESTART_HINT = (
    "Restart affected terminal apps if old glyphs still render "
    "(Terminal, iTerm2, Ghostty, WezTerm, Kitty, etc.)."
)


def refresh_font_cache(
    *,
    scope: str = "user",
    font_dirs: tuple[Path, ...] = (),
    platform_name: str | None = None,
    runner: CommandRunner | None = None,
    which: Callable[[str], str | None] | None = None,
) -> FontCacheRefreshResult:
    if scope not in {"user", "system"}:
        raise FontCacheError(f"unsupported cache refresh scope: {scope}")
    if scope == "system" and font_dirs:
        raise FontCacheError("--font-dir cannot be used with system cache refresh")

    resolved_platform = platform_name or sys.platform
    command_runner = runner or _run_command
    executable_lookup = which or shutil.which

    if resolved_platform == "darwin":
        return _refresh_macos_user_cache(
            scope=scope,
            platform_name=resolved_platform,
            runner=command_runner,
            which=executable_lookup,
        )
    if resolved_platform.startswith("linux"):
        return _refresh_linux_cache(
            scope=scope,
            font_dirs=font_dirs,
            platform_name=resolved_platform,
            runner=command_runner,
            which=executable_lookup,
        )
    if resolved_platform.startswith("win"):
        if scope == "system":
            raise FontCacheError("system cache refresh is not supported on Windows")
        return FontCacheRefreshResult(
            platform=resolved_platform,
            scope=scope,
            commands=(),
            restart_hint="No automatic Windows font cache refresh is available yet. "
            "Reinstall or restart apps that still show stale glyphs.",
        )

    raise FontCacheError(f"unsupported platform for font cache refresh: {resolved_platform}")


def _refresh_macos_user_cache(
    *,
    scope: str,
    platform_name: str,
    runner: CommandRunner,
    which: Callable[[str], str | None],
) -> FontCacheRefreshResult:
    if scope == "system":
        raise FontCacheError("system cache refresh is not supported on macOS")
    if which("atsutil") is None:
        raise FontCacheError("atsutil is required to refresh macOS font caches")
    commands = (
        ("atsutil", "databases", "-removeUser"),
        ("atsutil", "server", "-shutdown"),
        ("atsutil", "server", "-ping"),
    )
    _run_commands(commands, runner)
    return FontCacheRefreshResult(
        platform=platform_name,
        scope=scope,
        commands=commands,
        restart_hint=TERMINAL_RESTART_HINT,
    )


def _refresh_linux_cache(
    *,
    scope: str,
    font_dirs: tuple[Path, ...],
    platform_name: str,
    runner: CommandRunner,
    which: Callable[[str], str | None],
) -> FontCacheRefreshResult:
    if which("fc-cache") is None:
        raise FontCacheError("fc-cache is required to refresh Linux font caches")
    scoped_dirs = _validated_dirs(font_dirs) if scope == "user" else ()
    command = (
        ("fc-cache", "-f", "-s")
        if scope == "system"
        else ("fc-cache", "-f", *(str(path) for path in scoped_dirs))
    )
    commands = (command,)
    _run_commands(commands, runner)
    return FontCacheRefreshResult(
        platform=platform_name,
        scope=scope,
        commands=commands,
        restart_hint=TERMINAL_RESTART_HINT,
    )


def _validated_dirs(font_dirs: tuple[Path, ...]) -> tuple[Path, ...]:
    unique = []
    seen = set()
    for directory in font_dirs:
        resolved = directory.resolve()
        if not resolved.is_dir():
            raise FontCacheError(f"font directory does not exist: {directory}")
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return tuple(unique)


def _run_commands(commands: tuple[tuple[str, ...], ...], runner: CommandRunner) -> None:
    for command in commands:
        try:
            runner(list(command))
        except (OSError, subprocess.CalledProcessError) as error:
            raise FontCacheError(f"font cache refresh failed: {error}") from error


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, text=True, capture_output=True)
