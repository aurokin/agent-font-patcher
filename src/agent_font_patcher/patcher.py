from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import struct
import tempfile
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from defusedxml import ElementTree as SafeElementTree
from defusedxml.common import DefusedXmlException
from fontTools.pens.basePen import PenError
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont, TTLibError
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
from fontTools.misc.transform import Transform
from fontTools.svgLib.path import parse_path

from agent_font_patcher.manifest import Manifest, codepoint_to_int


PATCH_METADATA_NAME_ID = 256
PATCH_METADATA_NAME_IDS = range(256, 384)
PATCHER_VERSION = "0.1.0"
REQUIRED_METADATA_KEYS = {
    "project",
    "patcher_version",
    "manifest_version",
    "codepoint_range",
    "patched_codepoints",
    "source_font_name",
    "source_font_hash",
    "patched_at",
}
PRIVATE_USE_RANGES = (
    (0xE000, 0xF8FF),
    (0xF0000, 0xFFFFD),
    (0x100000, 0x10FFFD),
)
FONT_PARSE_ERRORS = (AssertionError, TTLibError, struct.error, zlib.error)
SVG_NUMBER_PATTERN = (
    r"[+-]?(?:(?:(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)|"
    r"(?:\.[0-9]+(?:[eE][+-]?[0-9]+)?))"
)
SVG_PATH_COMMANDS = "MmZzLlHhVvCcSsQqTtAa"
SVG_LINE_PATH_COMMANDS = frozenset("MmZzLlHhVv")
SVG_PATH_TOKEN_PATTERN = re.compile(
    rf"(?P<command>[{SVG_PATH_COMMANDS}])|"
    rf"(?P<number>{SVG_NUMBER_PATTERN})|"
    r"(?P<separator>[,\s]+)"
)
SVG_NUMBER_FULL_PATTERN = re.compile(SVG_NUMBER_PATTERN)
XML_DEFAULT_NAMESPACE_PATTERN = re.compile(br"\sxmlns\s*=\s*(['\"])(.*?)\1")
XML_DECLARATION_PATTERN = re.compile(
    br"<\?xml\s+version\s*=\s*(['\"])1\.0\1"
    br"(?:\s+encoding\s*=\s*(['\"])UTF-8\2)?"
    br"(?:\s+standalone\s*=\s*(['\"])(?:yes|no)\3)?"
    br"\s*\?>",
    re.IGNORECASE,
)
SVG_MALFORMED_SEPARATOR_PATTERN = re.compile(r",\s*(?:,|[A-Za-z]|$)|[A-Za-z]\s*,")
SVG_VIEWBOX_MALFORMED_SEPARATOR_PATTERN = re.compile(r"^\s*,|,\s*,|,\s*$")
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
UNSUPPORTED_PATH_ATTRIBUTES = {
    "clip-path",
    "clip-rule",
    "display",
    "fill",
    "fill-rule",
    "filter",
    "mask",
    "opacity",
    "stroke",
    "stroke-dasharray",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-miterlimit",
    "stroke-width",
    "visibility",
}
SVG_ALLOWED_ATTRIBUTES = {
    "svg": {"viewBox"},
    "g": set(),
    "path": {"d"},
}
GLYF_COORDINATE_MIN = -32768
GLYF_COORDINATE_MAX = 32767
SVG_GLYPH_TARGET_EM_FRACTION = 0.84
SVG_GLYPH_MAX_ADVANCE_RATIO = 1.4
SVG_GLYPH_OVERHANG_TOLERANCE_ADVANCE_FRACTION = 0.05


class PatchError(ValueError):
    """Raised when a font cannot be patched."""


@dataclass(frozen=True)
class PatchResult:
    source_path: Path
    output_path: Path
    patched_codepoints: tuple[str, ...]
    metadata: dict[str, Any]
    backup_path: Path | None = None


def patch_font_branch(
    source_path: Path,
    output_dir: Path,
    manifest: Manifest,
    *,
    use_placeholder_glyphs: bool = False,
    asset_base_dir: Path | None = None,
) -> PatchResult:
    if manifest.project != "agent-font-patcher":
        raise PatchError("manifest project must be agent-font-patcher")
    _validate_manifest_private_use(manifest)
    _reject_font_collection(source_path)

    output_path = _branch_output_path(source_path, output_dir)
    if output_path.exists() or output_path.is_symlink():
        raise PatchError(f"output already exists: {output_path}")

    font: TTFont | None = None
    try:
        with source_path.open("rb") as font_file:
            font = TTFont(font_file, lazy=False, fontNumber=0)
    except (OSError, *FONT_PARSE_ERRORS) as error:
        raise PatchError(f"unable to read font: {error}") from error

    try:
        patched_codepoints, metadata = _patch_font(
            font=font,
            source_path=source_path,
            manifest=manifest,
            use_placeholder_glyphs=use_placeholder_glyphs,
            asset_base_dir=asset_base_dir,
            rename_branch=True,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        _save_font_exclusive(font, output_path)
    except (OSError, KeyError, UnicodeError, *FONT_PARSE_ERRORS) as error:
        raise PatchError(f"unable to patch font: {error}") from error
    finally:
        font.close()

    return PatchResult(
        source_path=source_path,
        output_path=output_path,
        patched_codepoints=patched_codepoints,
        metadata=metadata,
    )


def patch_font_in_place(
    source_path: Path,
    manifest: Manifest,
    *,
    use_placeholder_glyphs: bool = False,
    asset_base_dir: Path | None = None,
    create_backup: bool = True,
    backup_dir: Path | None = None,
) -> PatchResult:
    if manifest.project != "agent-font-patcher":
        raise PatchError("manifest project must be agent-font-patcher")
    _validate_manifest_private_use(manifest)
    if source_path.is_symlink():
        raise PatchError("in-place patching does not support symlinked font paths")
    _reject_font_collection(source_path)
    if not os.access(source_path, os.W_OK):
        raise PatchError(f"font is not writable: {source_path}")
    if not os.access(source_path.parent, os.W_OK):
        raise PatchError(f"font directory is not writable: {source_path.parent}")

    backup_path = _backup_path(source_path, backup_dir) if create_backup else None
    if backup_path is not None and (backup_path.exists() or backup_path.is_symlink()):
        raise PatchError(f"backup already exists: {backup_path}")

    font: TTFont | None = None
    try:
        with source_path.open("rb") as font_file:
            font = TTFont(font_file, lazy=False, fontNumber=0)
    except (OSError, *FONT_PARSE_ERRORS) as error:
        raise PatchError(f"unable to read font: {error}") from error

    try:
        patched_codepoints, metadata = _patch_font(
            font=font,
            source_path=source_path,
            manifest=manifest,
            use_placeholder_glyphs=use_placeholder_glyphs,
            asset_base_dir=asset_base_dir,
            rename_branch=False,
        )
        backup_created = False
        try:
            if backup_path is not None:
                _create_backup(source_path, backup_path)
                backup_created = True
            _save_font_replace(font, source_path, stat_source=source_path)
        except Exception:
            if backup_created and backup_path is not None:
                backup_path.unlink(missing_ok=True)
            raise
    except (OSError, KeyError, UnicodeError, *FONT_PARSE_ERRORS) as error:
        raise PatchError(f"unable to patch font: {error}") from error
    finally:
        font.close()

    return PatchResult(
        source_path=source_path,
        output_path=source_path,
        patched_codepoints=patched_codepoints,
        metadata=metadata,
        backup_path=backup_path,
    )


def restore_font_backup(font_path: Path, *, backup_dir: Path | None = None) -> Path:
    if font_path.is_symlink():
        raise PatchError("restore does not support symlinked font paths")
    backup_path = _backup_path(font_path, backup_dir)
    if not backup_path.exists() or backup_path.is_symlink():
        raise PatchError(f"backup does not exist: {backup_path}")
    if not os.access(font_path.parent, os.W_OK):
        raise PatchError(f"font directory is not writable: {font_path.parent}")
    try:
        _restore_backup(backup_path, font_path)
    except OSError as error:
        raise PatchError(f"unable to restore font: {error}") from error
    return backup_path


def read_patch_metadata(path: Path) -> dict[str, Any] | None:
    font: TTFont | None = None
    try:
        with path.open("rb") as font_file:
            font = TTFont(font_file, lazy=False, fontNumber=0)
        for record in font["name"].names:
            if record.nameID not in PATCH_METADATA_NAME_IDS:
                continue
            try:
                value = record.toUnicode()
                metadata = json.loads(value)
            except (UnicodeError, json.JSONDecodeError):
                continue
            if _is_patch_metadata(metadata):
                return metadata
    except (OSError, KeyError, *FONT_PARSE_ERRORS):
        return None
    finally:
        if font is not None:
            font.close()
    return None


def _branch_output_path(source_path: Path, output_dir: Path) -> Path:
    return output_dir / f"{source_path.stem}-Agent{source_path.suffix}"


def _backup_path(source_path: Path, backup_dir: Path | None) -> Path:
    backup_name = f"{source_path.name}.agent-font-patcher-backup"
    if backup_dir is None:
        return source_path.with_name(backup_name)
    return backup_dir / backup_name


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _reject_font_collection(path: Path) -> None:
    try:
        with path.open("rb") as source_file:
            header = source_file.read(4)
    except OSError as error:
        raise PatchError(f"unable to read font: {error}") from error
    if header == b"ttcf":
        raise PatchError("branch-off patching does not support font collections yet")


def _require_true_type_outline(font: TTFont) -> None:
    if "glyf" not in font or "hmtx" not in font:
        raise PatchError("only TrueType glyf fonts are supported by this patch mode")


def _validate_manifest_private_use(manifest: Manifest) -> None:
    _require_private_use_interval(manifest.range_start, manifest.range_end, "manifest range")
    for block in manifest.blocks:
        _require_private_use_interval(block.start, block.end, f"manifest block {block.name}")
    for icon in manifest.icons:
        if not _is_private_use_codepoint(codepoint_to_int(icon.codepoint)):
            raise PatchError(f"manifest codepoint must be private-use: {icon.codepoint}")


def _is_patch_metadata(metadata: object) -> bool:
    if not isinstance(metadata, dict):
        return False
    if metadata.get("project") != "agent-font-patcher":
        return False
    if not REQUIRED_METADATA_KEYS.issubset(metadata.keys()):
        return False
    return isinstance(metadata.get("patched_codepoints"), list)


def _patch_font(
    *,
    font: TTFont,
    source_path: Path,
    manifest: Manifest,
    use_placeholder_glyphs: bool,
    asset_base_dir: Path | None,
    rename_branch: bool,
) -> tuple[tuple[str, ...], dict[str, Any]]:
    _require_true_type_outline(font)
    source_hash = _sha256_file(source_path)
    source_name = _font_full_name(font) or source_path.stem
    if rename_branch:
        _rename_branch_family(font)
    patched_codepoints = _add_available_manifest_glyphs(
        font,
        manifest,
        use_placeholder_glyphs=use_placeholder_glyphs,
        asset_base_dir=asset_base_dir,
    )
    if not patched_codepoints:
        raise PatchError("manifest does not contain any available glyph assets")
    metadata = _patch_metadata(
        manifest=manifest,
        patched_codepoints=patched_codepoints,
        source_font_name=source_name,
        source_hash=source_hash,
        use_placeholder_glyphs=use_placeholder_glyphs,
    )
    _write_patch_metadata(font, metadata)
    return patched_codepoints, metadata


def _add_available_manifest_glyphs(
    font: TTFont,
    manifest: Manifest,
    *,
    use_placeholder_glyphs: bool,
    asset_base_dir: Path | None,
) -> tuple[str, ...]:
    patched: list[str] = []
    for icon in manifest.icons:
        if icon.asset_status != "available":
            continue
        codepoint = codepoint_to_int(icon.codepoint)
        glyph_name = f"agent.{icon.id.replace('-', '_')}"
        if glyph_name in font.getGlyphOrder():
            raise PatchError(f"glyph name already exists: {glyph_name}")
        if use_placeholder_glyphs:
            _add_placeholder_glyph(font, glyph_name)
        else:
            if icon.source is None:
                raise PatchError(f"icon {icon.id} does not include a source SVG path")
            _add_svg_glyph(font, glyph_name, _resolve_asset_path(icon.source, asset_base_dir))
        _map_codepoint(font, codepoint, glyph_name)
        patched.append(icon.codepoint)
    return tuple(patched)


def _is_private_use_codepoint(codepoint: int) -> bool:
    return any(start <= codepoint <= end for start, end in PRIVATE_USE_RANGES)


def _require_private_use_interval(start: str, end: str, label: str) -> None:
    start_value = codepoint_to_int(start)
    end_value = codepoint_to_int(end)
    if not any(
        private_start <= start_value <= end_value <= private_end
        for private_start, private_end in PRIVATE_USE_RANGES
    ):
        raise PatchError(f"{label} must stay within one private-use range: {start}-{end}")


def _add_placeholder_glyph(font: TTFont, glyph_name: str) -> None:
    glyph_order = font.getGlyphOrder()
    if glyph_name not in glyph_order:
        font.setGlyphOrder([*glyph_order, glyph_name])

    units_per_em = int(font["head"].unitsPerEm)
    advance_width = _default_advance_width(font)
    inset_x = max(advance_width // 5, 1)
    high_x = max(advance_width - inset_x, inset_x + 1)
    mid_x = advance_width // 2
    inset_y = max(units_per_em // 5, 1)
    high_y = max(units_per_em - inset_y, inset_y + 1)
    mid_y = units_per_em // 2

    pen = TTGlyphPen(None)
    pen.moveTo((mid_x, high_y))
    pen.lineTo((high_x, mid_y))
    pen.lineTo((mid_x, inset_y))
    pen.lineTo((inset_x, mid_y))
    pen.closePath()
    font["glyf"][glyph_name] = pen.glyph()
    font["hmtx"][glyph_name] = (advance_width, 0)


SvgAssetPath = Path | Traversable


def _resolve_asset_path(source: str, asset_base_dir: Path | None) -> SvgAssetPath:
    path = Path(source)
    if path.is_absolute() or asset_base_dir is None:
        if asset_base_dir is None and not path.is_absolute():
            packaged_asset = resources.files("agent_font_patcher.data").joinpath(source)
            if packaged_asset.is_file():
                return packaged_asset
            if source.startswith("assets/"):
                raise PatchError(f"packaged SVG asset not found: {source}")
        return path
    return asset_base_dir / path


def _add_svg_glyph(font: TTFont, glyph_name: str, svg_path: SvgAssetPath) -> None:
    svg = _read_svg(svg_path)
    glyph_order = font.getGlyphOrder()
    font.setGlyphOrder([*glyph_order, glyph_name])

    units_per_em = int(font["head"].unitsPerEm)
    advance_width = _default_advance_width(font)
    vertical_min, vertical_max = _glyph_vertical_bounds(font, units_per_em)
    vertical_height = vertical_max - vertical_min
    raw_transform = Transform(1, 0, 0, -1, -svg.viewbox_min_x, svg.viewbox_height + svg.viewbox_min_y)
    raw_glyph = _parse_svg_glyph(svg, svg_path, raw_transform)
    _validate_svg_glyph(
        raw_glyph,
        svg_path,
        font["glyf"],
        min_x=-1,
        max_x=svg.viewbox_width + 1,
        min_y=-1,
        max_y=svg.viewbox_height + 1,
    )

    raw_width = raw_glyph.xMax - raw_glyph.xMin
    raw_height = raw_glyph.yMax - raw_glyph.yMin
    target_width = min(
        units_per_em * SVG_GLYPH_TARGET_EM_FRACTION,
        advance_width * SVG_GLYPH_MAX_ADVANCE_RATIO,
    )
    target_height = vertical_height * SVG_GLYPH_TARGET_EM_FRACTION
    scale = min(target_width / raw_width, target_height / raw_height)
    offset_x = (advance_width - raw_width * scale) / 2 - raw_glyph.xMin * scale
    offset_y = vertical_min + (vertical_height - raw_height * scale) / 2 - raw_glyph.yMin * scale
    transform = Transform(
        scale,
        0,
        0,
        -scale,
        offset_x - svg.viewbox_min_x * scale,
        offset_y + (svg.viewbox_height + svg.viewbox_min_y) * scale,
    )
    glyph = _parse_svg_glyph(svg, svg_path, transform)
    max_horizontal_overhang = max(
        math.ceil(
            (target_width - advance_width) / 2
            + advance_width * SVG_GLYPH_OVERHANG_TOLERANCE_ADVANCE_FRACTION
        ),
        0,
    )
    _validate_svg_glyph(
        glyph,
        svg_path,
        font["glyf"],
        min_x=-max_horizontal_overhang,
        max_x=advance_width + max_horizontal_overhang,
        min_y=vertical_min,
        max_y=vertical_max,
    )
    font["glyf"][glyph_name] = glyph
    font["hmtx"][glyph_name] = (advance_width, int(glyph.xMin))


def _glyph_vertical_bounds(font: TTFont, units_per_em: int) -> tuple[int, int]:
    ascent = int(getattr(font["hhea"], "ascent", units_per_em))
    descent = int(getattr(font["hhea"], "descent", 0))
    if ascent <= 0:
        return 0, units_per_em
    min_y = max(descent, -units_per_em) if descent < 0 else 0
    max_y = min(ascent, units_per_em)
    if max_y <= min_y:
        return 0, units_per_em
    return min_y, max_y


def _parse_svg_glyph(svg: SvgPathData, svg_path: SvgAssetPath, transform: Transform) -> object:
    pen = TTGlyphPen(None)
    transformed_pen = TransformPen(pen, transform)
    for path_data in svg.paths:
        _validate_svg_path_text(path_data, svg_path)
        try:
            parse_path(path_data, transformed_pen)
        except (AssertionError, AttributeError, IndexError, OverflowError, TypeError, ValueError) as error:
            raise PatchError(f"unable to parse SVG path data {svg_path}: {error}") from error
    try:
        glyph = pen.glyph()
    except (OverflowError, PenError, ValueError) as error:
        raise PatchError(f"unable to parse SVG path data {svg_path}: {error}") from error
    return glyph


@dataclass(frozen=True)
class SvgPathData:
    paths: tuple[str, ...]
    viewbox_min_x: float
    viewbox_min_y: float
    viewbox_width: float
    viewbox_height: float


def _read_svg(svg_path: SvgAssetPath) -> SvgPathData:
    try:
        svg_data = svg_path.read_bytes()
        svg_data = _normalize_svg_data(svg_data, svg_path)
        _reject_unsupported_xml_constructs(svg_data, svg_path)
        root = SafeElementTree.fromstring(svg_data)
    except (OSError, DefusedXmlException, SafeElementTree.ParseError) as error:
        raise PatchError(f"unable to read SVG asset {svg_path}: {error}") from error

    root_namespace, root_tag_name = _split_xml_tag(root.tag)
    if root_namespace not in (None, SVG_NAMESPACE):
        raise PatchError(f"SVG asset uses unsupported elements: {svg_path}")
    if root_tag_name != "svg":
        raise PatchError(f"SVG asset uses unsupported elements: {svg_path}")
    viewbox = _read_viewbox(root, svg_path)
    paths = []
    for index, element in enumerate(root.iter()):
        namespace, tag_name = _split_xml_tag(element.tag)
        if namespace not in (None, SVG_NAMESPACE):
            raise PatchError(f"SVG asset uses unsupported elements: {svg_path}")
        if tag_name not in SVG_ALLOWED_ATTRIBUTES:
            raise PatchError(f"SVG asset uses unsupported elements: {svg_path}")
        if tag_name == "svg" and index != 0:
            raise PatchError(f"SVG asset uses unsupported elements: {svg_path}")
        if (element.text and element.text.strip()) or (element.tail and element.tail.strip()):
            raise PatchError(f"SVG asset uses unsupported text content: {svg_path}")
        style = element.attrib.get("style", "")
        if "transform" in style.lower():
            raise PatchError(f"SVG asset uses unsupported transforms: {svg_path}")
        if style:
            raise PatchError(f"SVG asset uses unsupported style declarations: {svg_path}")
        if "transform" in element.attrib:
            raise PatchError(f"SVG asset uses unsupported transforms: {svg_path}")
        if tag_name == "style":
            raise PatchError(f"SVG asset uses unsupported style declarations: {svg_path}")
        if tag_name == "path" and list(element):
            raise PatchError(f"SVG asset uses unsupported elements: {svg_path}")
        unsupported_attributes = sorted(set(element.attrib) & UNSUPPORTED_PATH_ATTRIBUTES)
        if unsupported_attributes:
            raise PatchError(
                f"SVG element uses unsupported attributes: {', '.join(unsupported_attributes)}"
            )
        unsupported_attributes = sorted(set(element.attrib) - SVG_ALLOWED_ATTRIBUTES[tag_name])
        if unsupported_attributes:
            raise PatchError(
                f"SVG element uses unsupported attributes: {', '.join(unsupported_attributes)}"
            )
        if tag_name != "path":
            continue
        path_data = element.attrib.get("d")
        if path_data and path_data.strip():
            paths.append(path_data)
    if not paths:
        raise PatchError(f"SVG asset does not contain path data: {svg_path}")
    return SvgPathData(
        paths=tuple(paths),
        viewbox_min_x=viewbox[0],
        viewbox_min_y=viewbox[1],
        viewbox_width=viewbox[2],
        viewbox_height=viewbox[3],
    )


def _validate_svg_path_text(path_data: str, svg_path: SvgAssetPath) -> None:
    if SVG_MALFORMED_SEPARATOR_PATTERN.search(path_data):
        raise PatchError(f"unable to parse SVG path data {svg_path}: malformed separator")
    tokens = []
    position = 0
    while position < len(path_data):
        match = SVG_PATH_TOKEN_PATTERN.match(path_data, position)
        if match is None:
            raise PatchError(f"unable to parse SVG path data {svg_path}: invalid token")
        if match.lastgroup == "number":
            coordinate = float(match.group())
            if not math.isfinite(coordinate):
                raise PatchError(f"unable to parse SVG path data {svg_path}: non-finite coordinate")
            if coordinate < GLYF_COORDINATE_MIN or coordinate > GLYF_COORDINATE_MAX:
                raise PatchError(f"unable to parse SVG path data {svg_path}: out-of-range coordinate")
        if match.lastgroup in {"command", "number"}:
            tokens.append(match.group())
        position = match.end()
    _validate_svg_path_geometry(path_data, svg_path)


def _validate_svg_path_geometry(path_data: str, svg_path: SvgAssetPath) -> None:
    pen = _SvgGeometryPen(svg_path)
    try:
        parse_path(path_data, pen)
        pen.finish()
    except PatchError:
        raise
    except (AssertionError, AttributeError, IndexError, OverflowError, TypeError, ValueError) as error:
        raise PatchError(f"unable to parse SVG path data {svg_path}: {error}") from error


class _SvgGeometryPen:
    def __init__(self, svg_path: SvgAssetPath) -> None:
        self.svg_path = svg_path
        self.subpath: list[tuple[float, float]] | None = None

    def moveTo(self, point: tuple[float, float]) -> None:
        self.finish()
        self.subpath = [point]

    def lineTo(self, point: tuple[float, float]) -> None:
        self._require_subpath().append(point)

    def curveTo(self, *points: tuple[float, float]) -> None:
        self._require_subpath().extend(points)

    def qCurveTo(self, *points: tuple[float, float] | None) -> None:
        subpath = self._require_subpath()
        subpath.extend(point for point in points if point is not None)

    def closePath(self) -> None:
        self.finish()

    def endPath(self) -> None:
        self.finish()

    def addComponent(self, glyph_name: str, transformation: object) -> None:
        raise PatchError(f"unable to parse SVG path data {self.svg_path}: invalid component")

    def finish(self) -> None:
        if self.subpath is None:
            return
        if not _points_have_area(self.subpath):
            raise PatchError(f"SVG asset produced an empty glyph: {self.svg_path}")
        self.subpath = None

    def _require_subpath(self) -> list[tuple[float, float]]:
        if self.subpath is None:
            raise PatchError(f"unable to parse SVG path data {self.svg_path}: missing moveto")
        return self.subpath


def _validate_svg_glyph(
    glyph: object,
    svg_path: SvgAssetPath,
    glyf_table: object,
    *,
    min_x: float,
    max_x: float,
    min_y: float,
    max_y: float,
) -> None:
    if getattr(glyph, "numberOfContours", 0) <= 0:
        raise PatchError(f"SVG asset produced an empty glyph: {svg_path}")
    for coordinate in getattr(glyph, "coordinates", ()):
        x, y = coordinate
        if (
            not math.isfinite(x)
            or not math.isfinite(y)
            or x < GLYF_COORDINATE_MIN
            or x > GLYF_COORDINATE_MAX
            or y < GLYF_COORDINATE_MIN
            or y > GLYF_COORDINATE_MAX
        ):
            raise PatchError(f"SVG asset produced out-of-range glyph coordinates: {svg_path}")
    try:
        glyph.recalcBounds(glyf_table)
    except (OverflowError, ValueError) as error:
        raise PatchError(f"unable to parse SVG path data {svg_path}: {error}") from error
    if (
        getattr(glyph, "xMin", 0) == getattr(glyph, "xMax", 0)
        or getattr(glyph, "yMin", 0) == getattr(glyph, "yMax", 0)
        or not _glyph_contours_have_area(glyph)
    ):
        raise PatchError(f"SVG asset produced an empty glyph: {svg_path}")
    if (
        getattr(glyph, "xMin", 0) < min_x
        or getattr(glyph, "xMax", 0) > max_x
        or getattr(glyph, "yMin", 0) < min_y
        or getattr(glyph, "yMax", 0) > max_y
    ):
        raise PatchError(f"SVG asset produced out-of-cell glyph bounds: {svg_path}")


def _glyph_contours_have_area(glyph: object) -> bool:
    coordinates = getattr(glyph, "coordinates", ())
    contour_ends = getattr(glyph, "endPtsOfContours", ())
    start = 0
    for end in contour_ends:
        contour = coordinates[start : end + 1]
        start = end + 1
        if len(contour) >= 3 and _points_have_area(contour):
            return True
    return False


def _points_have_area(points: Any) -> bool:
    if len(points) < 3:
        return False
    twice_area = 0.0
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        twice_area += x1 * y2 - x2 * y1
    return abs(twice_area) > 1e-6


def _read_viewbox(root: object, svg_path: SvgAssetPath) -> tuple[float, float, float, float]:
    viewbox = root.attrib.get("viewBox")
    if not viewbox:
        raise PatchError(f"SVG asset does not declare a viewBox: {svg_path}")
    if SVG_VIEWBOX_MALFORMED_SEPARATOR_PATTERN.search(viewbox):
        raise PatchError(f"SVG asset has an invalid viewBox: {svg_path}")
    parts = viewbox.replace(",", " ").split()
    if len(parts) != 4:
        raise PatchError(f"SVG asset has an invalid viewBox: {svg_path}")
    if not all(SVG_NUMBER_FULL_PATTERN.fullmatch(part) for part in parts):
        raise PatchError(f"SVG asset has an invalid viewBox: {svg_path}")
    try:
        min_x, min_y, width, height = (float(part) for part in parts)
    except ValueError as error:
        raise PatchError(f"SVG asset has an invalid viewBox: {svg_path}") from error
    if (
        not all(math.isfinite(value) for value in (min_x, min_y, width, height))
        or width <= 0
        or height <= 0
        or not _value_within_coordinate_range(min_x)
        or not _value_within_coordinate_range(min_y)
        or not _value_within_coordinate_range(min_x + width)
        or not _value_within_coordinate_range(min_y + height)
    ):
        raise PatchError(f"SVG asset has an invalid viewBox: {svg_path}")
    return min_x, min_y, width, height


def _reject_unsupported_xml_constructs(svg_data: bytes, svg_path: SvgAssetPath) -> None:
    lowered = svg_data.lower()
    if b"<!" in svg_data or b"&" in svg_data or b"xmlns:" in lowered:
        raise PatchError(f"SVG asset uses unsupported XML constructs: {svg_path}")
    for match in XML_DEFAULT_NAMESPACE_PATTERN.finditer(svg_data):
        if match.group(2).decode("ascii", errors="ignore") != SVG_NAMESPACE:
            raise PatchError(f"SVG asset uses unsupported XML constructs: {svg_path}")
    stripped = svg_data.lstrip()
    if stripped.startswith(b"<?xml"):
        declaration_end = stripped.find(b"?>")
        if declaration_end == -1:
            raise PatchError(f"SVG asset uses unsupported XML constructs: {svg_path}")
        declaration = stripped[: declaration_end + 2]
        if not XML_DECLARATION_PATTERN.fullmatch(declaration):
            raise PatchError(f"SVG asset uses unsupported XML constructs: {svg_path}")
        stripped = stripped[declaration_end + 2 :]
    if b"<?" in stripped:
        raise PatchError(f"SVG asset uses unsupported XML constructs: {svg_path}")


def _normalize_svg_data(svg_data: bytes, svg_path: SvgAssetPath) -> bytes:
    try:
        return svg_data.decode("utf-8-sig").encode("utf-8")
    except UnicodeDecodeError as error:
        raise PatchError(f"SVG asset must be UTF-8 encoded: {svg_path}") from error


def _value_within_coordinate_range(value: float) -> bool:
    return GLYF_COORDINATE_MIN <= value <= GLYF_COORDINATE_MAX


def _split_xml_tag(tag: str) -> tuple[str | None, str]:
    if tag.startswith("{"):
        namespace, local_name = tag[1:].split("}", 1)
        return namespace, local_name
    return None, tag


def _default_advance_width(font: TTFont) -> int:
    metrics = font["hmtx"].metrics
    if "space" in metrics:
        return int(metrics["space"][0])
    for glyph_name, metric in metrics.items():
        if glyph_name != ".notdef":
            return int(metric[0])
    return int(font["head"].unitsPerEm)


def _map_codepoint(font: TTFont, codepoint: int, glyph_name: str) -> None:
    cmap_table = font["cmap"]
    existing = {
        table.cmap[codepoint]
        for table in cmap_table.tables
        if table.isUnicode() and codepoint in table.cmap
    }
    if existing:
        raise PatchError(f"codepoint U+{codepoint:04X} already maps to {', '.join(sorted(existing))}")
    target_tables = [
        table
        for table in cmap_table.tables
        if table.isUnicode() and _cmap_can_encode_codepoint(table, codepoint)
    ]
    if codepoint > 0xFFFF and not any(table.format == 12 for table in target_tables):
        target_tables.append(_new_format_12_cmap(font))
    if not target_tables:
        target_tables.append(_new_format_12_cmap(font))
    for table in target_tables:
        table.cmap[codepoint] = glyph_name


def _cmap_can_encode_codepoint(table: CmapSubtable, codepoint: int) -> bool:
    if table.format == 0:
        return codepoint <= 0xFF
    if table.format in {2, 4, 6}:
        return codepoint <= 0xFFFF
    if table.format == 12:
        return codepoint <= 0x10FFFF
    return False


def _new_format_12_cmap(font: TTFont) -> CmapSubtable:
    table = CmapSubtable.newSubtable(12)
    table.platformID, table.platEncID, table.language = _available_cmap_identity(font)
    table.cmap = _best_unicode_cmap(font)
    font["cmap"].tables.append(table)
    return table


def _available_cmap_identity(font: TTFont) -> tuple[int, int, int]:
    used = {
        (table.platformID, table.platEncID, table.language)
        for table in font["cmap"].tables
    }
    for identity in ((3, 10, 0), (0, 6, 0), (0, 4, 0), (0, 3, 0)):
        if identity not in used:
            return identity
    language = 1
    while (3, 10, language) in used:
        language += 1
    return (3, 10, language)


def _best_unicode_cmap(font: TTFont) -> dict[int, str]:
    unicode_tables = [
        table for table in font["cmap"].tables if table.isUnicode() and table.format != 13
    ]
    if not unicode_tables:
        return {}
    best_table = max(unicode_tables, key=lambda table: (table.format in {12, 13}, len(table.cmap)))
    return dict(best_table.cmap)


def _rename_branch_family(font: TTFont) -> None:
    name_table = font["name"]
    family = _font_family_name(font) or "Agent Font"
    subfamily = _font_subfamily_name(font) or "Regular"
    agent_family = _agent_family_name(family)
    full_name = f"{agent_family} {subfamily}".strip()
    postscript_name = _postscript_name(full_name)
    replacements = {
        1: agent_family,
        3: f"{agent_family} {subfamily}; agent-font-patcher",
        4: full_name,
        6: postscript_name,
        16: agent_family,
    }
    for record in name_table.names:
        value = replacements.get(record.nameID)
        if value is not None:
            record.string = value.encode(record.getEncoding(), errors="replace")


def _agent_family_name(family: str) -> str:
    if " Nerd Font" in family:
        return family.replace(" Nerd Font", " Agent Nerd Font", 1)
    if "NerdFont" in family:
        return family.replace("NerdFont", "AgentNerdFont", 1)
    return f"{family} Agent"


def _postscript_name(name: str) -> str:
    safe = "".join(
        character
        for character in name
        if character.isascii() and (character.isalnum() or character == "-")
    )
    return safe[:63] or "AgentFont"


def _font_family_name(font: TTFont) -> str | None:
    return _first_name(font, (16, 1))


def _font_subfamily_name(font: TTFont) -> str | None:
    return _first_name(font, (17, 2))


def _font_full_name(font: TTFont) -> str | None:
    return _first_name(font, (4,))


def _first_name(font: TTFont, name_ids: tuple[int, ...]) -> str | None:
    name_table = font["name"]
    for name_id in name_ids:
        for record in name_table.names:
            if record.nameID != name_id:
                continue
            value = record.toUnicode()
            if value:
                return value
    return None


def _patch_metadata(
    manifest: Manifest,
    patched_codepoints: tuple[str, ...],
    source_font_name: str,
    source_hash: str,
    use_placeholder_glyphs: bool,
) -> dict[str, Any]:
    return {
        "project": manifest.project,
        "patcher_version": PATCHER_VERSION,
        "manifest_version": manifest.manifest_version,
        "codepoint_range": f"{manifest.range_start}-{manifest.range_end}",
        "patched_codepoints": list(patched_codepoints),
        "glyph_source": "placeholder" if use_placeholder_glyphs else "assets",
        "placeholder_glyphs": use_placeholder_glyphs,
        "source_font_name": source_font_name,
        "source_font_hash": source_hash,
        "patched_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def _save_font_exclusive(font: TTFont, output_path: Path) -> None:
    temp_path: Path | None = None
    temp_file = tempfile.NamedTemporaryFile(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        delete=False,
    )
    try:
        temp_path = Path(temp_file.name)
        temp_file.close()
        font.save(temp_path)
        os.link(temp_path, output_path)
    except FileExistsError as error:
        raise PatchError(f"output already exists: {output_path}") from error
    finally:
        if not temp_file.file.closed:
            temp_file.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _save_font_replace(font: TTFont, output_path: Path, *, stat_source: Path | None = None) -> None:
    temp_path: Path | None = None
    temp_file = tempfile.NamedTemporaryFile(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        delete=False,
    )
    try:
        temp_path = Path(temp_file.name)
        temp_file.close()
        font.save(temp_path)
        if stat_source is not None:
            _copy_file_metadata(stat_source, temp_path)
        os.replace(temp_path, output_path)
        temp_path = None
    finally:
        if not temp_file.file.closed:
            temp_file.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _create_backup(source_path: Path, backup_path: Path) -> None:
    temp_path: Path | None = None
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = tempfile.NamedTemporaryFile(
        dir=backup_path.parent,
        prefix=f".{backup_path.name}.",
        suffix=".tmp",
        delete=False,
    )
    try:
        temp_path = Path(temp_file.name)
        with source_path.open("rb") as source_file:
            with temp_file:
                shutil.copyfileobj(source_file, temp_file)
        _copy_file_metadata(source_path, temp_path)
        os.link(temp_path, backup_path)
    except FileExistsError as error:
        raise PatchError(f"backup already exists: {backup_path}") from error
    finally:
        if not temp_file.file.closed:
            temp_file.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _restore_backup(backup_path: Path, font_path: Path) -> None:
    temp_path: Path | None = None
    temp_file = tempfile.NamedTemporaryFile(
        dir=font_path.parent,
        prefix=f".{font_path.name}.restore.",
        suffix=".tmp",
        delete=False,
    )
    try:
        temp_path = Path(temp_file.name)
        with backup_path.open("rb") as backup_file:
            shutil.copyfileobj(backup_file, temp_file)
        temp_file.close()
        _copy_file_metadata(backup_path, temp_path)
        os.replace(temp_path, font_path)
        temp_path = None
    finally:
        if not temp_file.file.closed:
            temp_file.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _copy_file_metadata(source_path: Path, target_path: Path) -> None:
    source_stat = source_path.stat()
    chown = getattr(os, "chown", None)
    if chown is not None:
        try:
            chown(target_path, source_stat.st_uid, source_stat.st_gid)
        except PermissionError:
            target_stat = target_path.stat()
            if (target_stat.st_uid, target_stat.st_gid) != (source_stat.st_uid, source_stat.st_gid):
                raise
    shutil.copystat(source_path, target_path, follow_symlinks=False)


def _write_patch_metadata(font: TTFont, metadata: dict[str, Any]) -> None:
    _remove_existing_patch_metadata(font)
    metadata_json = json.dumps(metadata, sort_keys=True, separators=(",", ":"))
    font["name"].setName(metadata_json, _metadata_name_id(font), 3, 1, 0x409)


def _metadata_name_id(font: TTFont) -> int:
    occupied = {
        record.nameID
        for record in font["name"].names
        if (record.platformID, record.platEncID, record.langID) == (3, 1, 0x409)
    }
    for name_id in PATCH_METADATA_NAME_IDS:
        if name_id not in occupied:
            return name_id
    raise PatchError("no private name ID is available for patch metadata")


def _remove_existing_patch_metadata(font: TTFont) -> None:
    name_table = font["name"]
    kept_records = []
    for record in name_table.names:
        if record.nameID not in PATCH_METADATA_NAME_IDS:
            kept_records.append(record)
            continue
        try:
            metadata = json.loads(record.toUnicode())
        except (UnicodeError, json.JSONDecodeError):
            kept_records.append(record)
            continue
        if not _is_patch_metadata(metadata):
            kept_records.append(record)
    name_table.names = kept_records
