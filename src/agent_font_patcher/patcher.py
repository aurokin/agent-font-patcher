from __future__ import annotations

import hashlib
import json
import os
import struct
import tempfile
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, TTLibError
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable

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


class PatchError(ValueError):
    """Raised when a font cannot be patched."""


@dataclass(frozen=True)
class PatchResult:
    source_path: Path
    output_path: Path
    patched_codepoints: tuple[str, ...]
    metadata: dict[str, Any]


def patch_font_branch(
    source_path: Path,
    output_dir: Path,
    manifest: Manifest,
    *,
    use_placeholder_glyphs: bool = False,
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
        _require_true_type_outline(font)
        source_hash = _sha256_file(source_path)
        source_name = _font_full_name(font) or source_path.stem
        _rename_branch_family(font)
        patched_codepoints = _add_available_manifest_glyphs(
            font,
            manifest,
            use_placeholder_glyphs=use_placeholder_glyphs,
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


def _add_available_manifest_glyphs(
    font: TTFont,
    manifest: Manifest,
    *,
    use_placeholder_glyphs: bool,
) -> tuple[str, ...]:
    patched: list[str] = []
    for icon in manifest.icons:
        if icon.asset_status != "available":
            continue
        if not use_placeholder_glyphs:
            raise PatchError(
                "glyph asset ingestion is not implemented yet; pass "
                "--use-placeholder-glyphs for explicit test output"
        )
        codepoint = codepoint_to_int(icon.codepoint)
        glyph_name = f"agent.{icon.id.replace('-', '_')}"
        if glyph_name in font.getGlyphOrder():
            raise PatchError(f"glyph name already exists: {glyph_name}")
        _add_placeholder_glyph(font, glyph_name)
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
