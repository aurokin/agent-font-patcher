from __future__ import annotations

import os
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from fontTools.ttLib import TTCollection, TTFont, TTLibError


FONT_EXTENSIONS = {".otf", ".ttc", ".ttf"}
NERD_FONT_MARKERS = ("Nerd Font", " NFM", " NF ", " NFP", "NerdFont")
FONT_PARSE_ERRORS = (
    AssertionError,
    KeyError,
    OSError,
    TTLibError,
    UnicodeError,
    struct.error,
    zlib.error,
)


@dataclass(frozen=True)
class FontCandidate:
    path: Path
    family: str | None
    subfamily: str | None
    full_name: str | None
    postscript_name: str | None
    is_likely_nerd_font: bool
    is_writable: bool
    reason: str


def default_font_dirs(platform: str | None = None) -> tuple[Path, ...]:
    platform_name = platform or sys.platform
    home = Path.home()
    if platform_name == "darwin":
        return (
            home / "Library" / "Fonts",
            Path("/Library/Fonts"),
            Path("/opt/homebrew/share/fonts"),
            Path("/usr/local/share/fonts"),
        )
    if platform_name.startswith("linux"):
        xdg_data_home = Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share")
        xdg_data_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
        return (
            xdg_data_home / "fonts",
            home / ".fonts",
            *(Path(data_dir) / "fonts" for data_dir in xdg_data_dirs.split(":") if data_dir),
        )
    if platform_name.startswith("win"):
        font_dirs = []
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            font_dirs.append(Path(local_app_data) / "Microsoft" / "Windows" / "Fonts")
        font_dirs.append(Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts")
        return tuple(font_dirs)
    return ()


def discover_font_files(font_dirs: Iterable[Path]) -> list[Path]:
    font_files: list[Path] = []
    seen: set[Path] = set()
    for font_dir in font_dirs:
        if not font_dir.exists() or not font_dir.is_dir():
            continue
        for path in font_dir.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in FONT_EXTENSIONS:
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            font_files.append(path)
    return sorted(font_files)


def scan_fonts(font_dirs: Iterable[Path] | None = None) -> list[FontCandidate]:
    dirs = tuple(font_dirs) if font_dirs is not None else default_font_dirs()
    candidates = [inspect_font(path) for path in discover_font_files(dirs)]
    return [candidate for candidate in candidates if candidate.is_likely_nerd_font]


def inspect_font(path: Path) -> FontCandidate:
    if path.suffix.lower() == ".ttc":
        return _inspect_collection(path)
    return _inspect_single_font(path)


def _inspect_collection(path: Path) -> FontCandidate:
    try:
        with path.open("rb") as font_file:
            collection = TTCollection(font_file)
    except FONT_PARSE_ERRORS as error:
        return _unreadable_candidate(path, error)

    first_candidate: FontCandidate | None = None
    try:
        for font in collection.fonts:
            candidate = _candidate_from_font(path, font)
            if first_candidate is None:
                first_candidate = candidate
            if candidate.is_likely_nerd_font:
                return candidate
    except FONT_PARSE_ERRORS as error:
        return _unreadable_candidate(path, error)
    finally:
        for font in collection.fonts:
            font.close()

    return first_candidate or _unreadable_candidate(path, "empty font collection")


def _inspect_single_font(path: Path) -> FontCandidate:
    font: TTFont | None = None
    try:
        with path.open("rb") as font_file:
            font = TTFont(font_file, lazy=False, fontNumber=0)
    except FONT_PARSE_ERRORS as error:
        if font is not None:
            font.close()
        return _unreadable_candidate(path, error)

    try:
        return _candidate_from_font(path, font)
    except FONT_PARSE_ERRORS as error:
        return _unreadable_candidate(path, error)
    finally:
        font.close()


def _candidate_from_font(path: Path, font: TTFont) -> FontCandidate:
    names = _read_names(font)
    haystack = " ".join(value for value in names.values() if value)
    marker = next((marker for marker in NERD_FONT_MARKERS if marker in haystack), None)
    is_likely = marker is not None
    reason = f"name contains {marker!r}" if marker else "no Nerd Font marker"
    return FontCandidate(
        path=path,
        family=names.get("family"),
        subfamily=names.get("subfamily"),
        full_name=names.get("full_name"),
        postscript_name=names.get("postscript_name"),
        is_likely_nerd_font=is_likely,
        is_writable=os.access(path, os.W_OK),
        reason=reason if is_likely else "no Nerd Font marker",
    )


def _unreadable_candidate(path: Path, error: object) -> FontCandidate:
    return FontCandidate(
        path=path,
        family=None,
        subfamily=None,
        full_name=None,
        postscript_name=None,
        is_likely_nerd_font=False,
        is_writable=os.access(path, os.W_OK),
        reason=f"unreadable font: {error}",
    )


def _read_names(font: TTFont) -> dict[str, str | None]:
    name_table = font["name"]
    return {
        "family": _first_name(name_table, (16, 1)),
        "subfamily": _first_name(name_table, (17, 2)),
        "full_name": _first_name(name_table, (4,)),
        "postscript_name": _first_name(name_table, (6,)),
    }


def _first_name(name_table, name_ids: tuple[int, ...]) -> str | None:
    for name_id in name_ids:
        for record in name_table.names:
            if record.nameID == name_id:
                value = record.toUnicode().strip()
                if value:
                    return value
    return None
