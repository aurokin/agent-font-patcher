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


@dataclass(frozen=True, init=False)
class FontCandidate:
    path: Path
    family: str | None
    subfamily: str | None
    full_name: str | None
    postscript_name: str | None
    is_likely_nerd_font: bool
    is_readable: bool
    is_writable: bool
    reason: str

    __match_args__ = (
        "path",
        "family",
        "subfamily",
        "full_name",
        "postscript_name",
        "is_likely_nerd_font",
        "is_writable",
        "reason",
        "is_readable",
    )

    def __init__(
        self,
        path: Path,
        family: str | None,
        subfamily: str | None,
        full_name: str | None,
        postscript_name: str | None,
        is_likely_nerd_font: bool,
        *args: object,
        is_writable: bool | None = None,
        reason: str | None = None,
        is_readable: bool | None = None,
    ) -> None:
        parsed_is_writable: object
        parsed_reason: object
        parsed_is_readable: object
        if len(args) == 0:
            if is_writable is None or reason is None:
                raise TypeError("FontCandidate missing is_writable or reason")
            parsed_is_writable = is_writable
            parsed_reason = reason
            parsed_is_readable = True if is_readable is None else is_readable
        elif len(args) == 1:
            (first,) = args
            if is_writable is not None:
                if is_readable is not None:
                    raise TypeError("FontCandidate got multiple values for is_readable")
                if reason is None:
                    raise TypeError("FontCandidate missing reason")
                parsed_is_readable = first
                parsed_is_writable = is_writable
                parsed_reason = reason
            else:
                if reason is None:
                    raise TypeError("FontCandidate missing reason")
                parsed_is_writable = first
                parsed_reason = reason
                parsed_is_readable = True if is_readable is None else is_readable
        elif len(args) == 2:
            first, second = args
            if reason is not None:
                if is_readable is not None or is_writable is not None:
                    raise TypeError("FontCandidate positional and keyword fields overlap")
                parsed_is_readable = first
                parsed_is_writable = second
                parsed_reason = reason
            else:
                if is_readable is not None or is_writable is not None:
                    raise TypeError("FontCandidate positional and keyword fields overlap")
                if isinstance(second, str):
                    parsed_is_writable = first
                    parsed_reason = second
                    parsed_is_readable = True
                elif isinstance(second, bool):
                    raise TypeError("FontCandidate missing reason")
                else:
                    raise TypeError("FontCandidate missing reason")
        elif len(args) == 3:
            if is_readable is not None or is_writable is not None or reason is not None:
                raise TypeError("FontCandidate positional and keyword fields overlap")
            parsed_is_readable, parsed_is_writable, parsed_reason = args
        else:
            raise TypeError(f"FontCandidate expected 8 or 9 positional arguments, got {6 + len(args)}")

        object.__setattr__(self, "path", path)
        object.__setattr__(self, "family", family)
        object.__setattr__(self, "subfamily", subfamily)
        object.__setattr__(self, "full_name", full_name)
        object.__setattr__(self, "postscript_name", postscript_name)
        object.__setattr__(self, "is_likely_nerd_font", is_likely_nerd_font)
        object.__setattr__(self, "is_readable", parsed_is_readable)
        object.__setattr__(self, "is_writable", parsed_is_writable)
        object.__setattr__(self, "reason", parsed_reason)


@dataclass(frozen=True)
class CodepointReadResult:
    codepoints: frozenset[int]
    error: str | None = None

    @property
    def is_readable(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class CollectionFaceSelection:
    index: int | None
    candidate: FontCandidate


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


def read_font_codepoints(path: Path) -> CodepointReadResult:
    if path.suffix.lower() == ".ttc":
        return _read_collection_codepoints(path)
    return _read_single_font_codepoints(path)


def _read_font_codepoints_for_face(path: Path, font_number: int) -> CodepointReadResult:
    return _read_single_font_codepoints(path, font_number=font_number)


def _inspect_collection(path: Path) -> FontCandidate:
    return _select_collection_face(path).candidate


def _select_collection_face(path: Path) -> CollectionFaceSelection:
    try:
        with path.open("rb") as font_file:
            collection = TTCollection(font_file)
    except FONT_PARSE_ERRORS as error:
        return CollectionFaceSelection(None, _unreadable_candidate(path, error))

    first_selection: CollectionFaceSelection | None = None
    try:
        for index, font in enumerate(collection.fonts):
            candidate = _candidate_from_font(path, font)
            selection = CollectionFaceSelection(index, candidate)
            if first_selection is None:
                first_selection = selection
            if candidate.is_likely_nerd_font:
                return selection
    except FONT_PARSE_ERRORS as error:
        return CollectionFaceSelection(None, _unreadable_candidate(path, error))
    finally:
        for font in collection.fonts:
            font.close()

    return first_selection or CollectionFaceSelection(None, _unreadable_candidate(path, "empty font collection"))


def _read_collection_codepoints(path: Path) -> CodepointReadResult:
    selection = _select_collection_face(path)
    if selection.index is None:
        return _read_all_collection_codepoints(path)
    return _read_font_codepoints_for_face(path, selection.index)


def _read_all_collection_codepoints(path: Path) -> CodepointReadResult:
    try:
        with path.open("rb") as font_file:
            collection = TTCollection(font_file)
    except FONT_PARSE_ERRORS as error:
        return CodepointReadResult(frozenset(), str(error))

    if not collection.fonts:
        return CodepointReadResult(frozenset(), "empty font collection")

    codepoints: set[int] = set()
    try:
        for font in collection.fonts:
            codepoints.update(_read_cmap_codepoints(font))
    except FONT_PARSE_ERRORS as error:
        return CodepointReadResult(frozenset(), str(error))
    finally:
        for font in collection.fonts:
            font.close()

    return CodepointReadResult(frozenset(codepoints))


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


def _read_single_font_codepoints(path: Path, font_number: int = 0) -> CodepointReadResult:
    font: TTFont | None = None
    try:
        with path.open("rb") as font_file:
            font = TTFont(font_file, lazy=False, fontNumber=font_number)
    except FONT_PARSE_ERRORS as error:
        if font is not None:
            font.close()
        return CodepointReadResult(frozenset(), str(error))

    try:
        return CodepointReadResult(frozenset(_read_cmap_codepoints(font)))
    except FONT_PARSE_ERRORS as error:
        return CodepointReadResult(frozenset(), str(error))
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
        is_readable=True,
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
        is_readable=False,
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


def _read_cmap_codepoints(font: TTFont) -> set[int]:
    cmap_table = font["cmap"]
    codepoints: set[int] = set()
    for table in cmap_table.tables:
        codepoints.update(table.cmap.keys())
    return codepoints
