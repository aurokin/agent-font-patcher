from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources
from json import JSONDecodeError
from pathlib import Path
from typing import Any


CODEPOINT_PATTERN = re.compile(r"^U\+[0-9A-F]{4,6}$")


class ManifestError(ValueError):
    """Raised when the codepoint manifest is malformed."""


@dataclass(frozen=True)
class Icon:
    id: str
    display_name: str
    aliases: tuple[str, ...]
    category: str
    codepoint: str
    asset_status: str
    source: str | None
    license: str | None
    attribution: str | None

    @property
    def character(self) -> str:
        return chr(codepoint_to_int(self.codepoint))


@dataclass(frozen=True)
class CodepointBlock:
    name: str
    start: str
    end: str
    description: str

    def contains(self, codepoint: str) -> bool:
        value = codepoint_to_int(codepoint)
        return codepoint_to_int(self.start) <= value <= codepoint_to_int(self.end)


@dataclass(frozen=True)
class Manifest:
    schema_version: int
    manifest_version: str
    project: str
    range_start: str
    range_end: str
    range_description: str
    blocks: tuple[CodepointBlock, ...]
    icons: tuple[Icon, ...]

    def icon_by_id(self, icon_id: str) -> Icon | None:
        return next((icon for icon in self.icons if icon.id == icon_id), None)


def codepoint_to_int(codepoint: str) -> int:
    if not CODEPOINT_PATTERN.match(codepoint):
        raise ManifestError(f"Invalid codepoint format: {codepoint}")
    value = int(codepoint[2:], 16)
    if value > 0x10FFFF:
        raise ManifestError(f"Codepoint exceeds Unicode maximum: {codepoint}")
    if 0xD800 <= value <= 0xDFFF:
        raise ManifestError(f"Codepoint is a surrogate value: {codepoint}")
    return value


def load_manifest(path: Path | None = None) -> Manifest:
    try:
        if path is None:
            with resources.files("agent_font_patcher.data").joinpath("codepoints.json").open(
                encoding="utf-8"
            ) as manifest_file:
                raw = json.load(manifest_file)
        else:
            with path.open(encoding="utf-8") as manifest_file:
                raw = json.load(manifest_file)
    except OSError as error:
        raise ManifestError(f"Unable to read manifest: {error}") from error
    except JSONDecodeError as error:
        raise ManifestError(f"Manifest is not valid JSON: {error}") from error
    return parse_manifest(raw)


def parse_manifest(raw: Any) -> Manifest:
    if not isinstance(raw, dict):
        raise ManifestError("Manifest root must be a JSON object")
    required_top_level = {
        "schema_version",
        "manifest_version",
        "project",
        "range",
        "blocks",
        "icons",
    }
    missing = sorted(required_top_level - raw.keys())
    if missing:
        raise ManifestError(f"Manifest missing required keys: {', '.join(missing)}")

    font_range = raw["range"]
    if not isinstance(font_range, dict):
        raise ManifestError("Manifest range must be an object")
    range_start = _required_string(font_range, "start")
    range_end = _required_string(font_range, "end")
    range_description = _required_string(font_range, "description")
    if codepoint_to_int(range_start) > codepoint_to_int(range_end):
        raise ManifestError("Manifest range start must be less than or equal to end")

    raw_blocks = raw["blocks"]
    raw_icons = raw["icons"]
    if not isinstance(raw_blocks, list):
        raise ManifestError("Manifest blocks must be a list")
    if not isinstance(raw_icons, list):
        raise ManifestError("Manifest icons must be a list")

    blocks = tuple(_parse_block(block) for block in raw_blocks)
    icons = tuple(_parse_icon(icon) for icon in raw_icons)
    _validate_unique_blocks(blocks)
    _validate_blocks_in_range(blocks, range_start, range_end)
    _validate_block_layout(blocks)
    _validate_unique_icons(icons)
    _validate_icons_in_range(icons, range_start, range_end)
    _validate_icons_in_blocks(icons, blocks)

    schema_version = raw["schema_version"]
    if type(schema_version) is not int or schema_version != 1:
        raise ManifestError("Manifest schema_version must be integer 1")

    return Manifest(
        schema_version=schema_version,
        manifest_version=_required_string(raw, "manifest_version"),
        project=_required_string(raw, "project"),
        range_start=range_start,
        range_end=range_end,
        range_description=range_description,
        blocks=blocks,
        icons=icons,
    )


def _parse_block(raw: dict[str, Any]) -> CodepointBlock:
    if not isinstance(raw, dict):
        raise ManifestError("Manifest block must be an object")
    block = CodepointBlock(
        name=_required_string(raw, "name"),
        start=_required_string(raw, "start"),
        end=_required_string(raw, "end"),
        description=_required_string(raw, "description"),
    )
    if codepoint_to_int(block.start) > codepoint_to_int(block.end):
        raise ManifestError(f"Block {block.name} start must be less than or equal to end")
    return block


def _parse_icon(raw: dict[str, Any]) -> Icon:
    if not isinstance(raw, dict):
        raise ManifestError("Manifest icon must be an object")
    aliases = raw.get("aliases", [])
    if not isinstance(aliases, list) or not all(isinstance(alias, str) for alias in aliases):
        raise ManifestError(f"Icon {_required_string(raw, 'id')} aliases must be a list of strings")
    asset_status = raw.get("asset_status", "available")
    if not isinstance(asset_status, str):
        raise ManifestError(f"Icon {_required_string(raw, 'id')} asset_status must be a string")
    if asset_status not in {"available", "reserved", "deprecated"}:
        raise ManifestError(
            f"Icon {_required_string(raw, 'id')} asset_status must be available, reserved, or deprecated"
        )
    source = _optional_string(raw, "source")
    license_name = _optional_string(raw, "license")
    attribution = _optional_string(raw, "attribution")
    if asset_status == "available" and not all((source, license_name, attribution)):
        raise ManifestError(
            f"Icon {_required_string(raw, 'id')} must include source, license, and attribution"
        )
    return Icon(
        id=_required_string(raw, "id"),
        display_name=_required_string(raw, "display_name"),
        aliases=tuple(aliases),
        category=_required_string(raw, "category"),
        codepoint=_required_string(raw, "codepoint"),
        asset_status=asset_status,
        source=source,
        license=license_name,
        attribution=attribution,
    )


def _required_string(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ManifestError(f"Expected non-empty string for key: {key}")
    return value


def _optional_string(raw: dict[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ManifestError(f"Expected non-empty string for key: {key}")
    return value


def _validate_unique_icons(icons: tuple[Icon, ...]) -> None:
    seen_ids: set[str] = set()
    seen_codepoints: set[int] = set()
    for icon in icons:
        codepoint_value = codepoint_to_int(icon.codepoint)
        if icon.id in seen_ids:
            raise ManifestError(f"Duplicate icon id: {icon.id}")
        if codepoint_value in seen_codepoints:
            raise ManifestError(f"Duplicate codepoint: {icon.codepoint}")
        seen_ids.add(icon.id)
        seen_codepoints.add(codepoint_value)


def _validate_unique_blocks(blocks: tuple[CodepointBlock, ...]) -> None:
    seen_names: set[str] = set()
    for block in blocks:
        if block.name in seen_names:
            raise ManifestError(f"Duplicate block name: {block.name}")
        seen_names.add(block.name)


def _validate_blocks_in_range(
    blocks: tuple[CodepointBlock, ...], range_start: str, range_end: str
) -> None:
    start = codepoint_to_int(range_start)
    end = codepoint_to_int(range_end)
    for block in blocks:
        block_start = codepoint_to_int(block.start)
        block_end = codepoint_to_int(block.end)
        if block_start < start or block_end > end:
            raise ManifestError(f"Block {block.name} is outside manifest range")


def _validate_block_layout(blocks: tuple[CodepointBlock, ...]) -> None:
    sorted_blocks = sorted(blocks, key=lambda block: codepoint_to_int(block.start))
    previous: CodepointBlock | None = None
    for block in sorted_blocks:
        if previous and codepoint_to_int(block.start) <= codepoint_to_int(previous.end):
            raise ManifestError(f"Block {block.name} overlaps block {previous.name}")
        previous = block


def _validate_icons_in_range(icons: tuple[Icon, ...], range_start: str, range_end: str) -> None:
    start = codepoint_to_int(range_start)
    end = codepoint_to_int(range_end)
    for icon in icons:
        value = codepoint_to_int(icon.codepoint)
        if value < start or value > end:
            raise ManifestError(f"Icon {icon.id} codepoint is outside manifest range")


def _validate_icons_in_blocks(icons: tuple[Icon, ...], blocks: tuple[CodepointBlock, ...]) -> None:
    block_by_name = {block.name: block for block in blocks}
    for icon in icons:
        block = block_by_name.get(icon.category)
        if block is None:
            raise ManifestError(f"Icon {icon.id} references unknown category: {icon.category}")
        if not block.contains(icon.codepoint):
            raise ManifestError(f"Icon {icon.id} codepoint is outside category block")
