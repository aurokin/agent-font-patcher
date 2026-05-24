from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_font_patcher.manifest import Icon, Manifest, codepoint_to_int, load_manifest
from agent_font_patcher.scanner import FontCandidate, inspect_font, read_font_codepoints


@dataclass(frozen=True)
class IconCoverage:
    icon: Icon
    is_present: bool


@dataclass(frozen=True)
class FontInspection:
    candidate: FontCandidate
    manifest: Manifest
    icon_coverage: tuple[IconCoverage, ...]
    codepoints_error: str | None
    reserved_coverage: tuple[IconCoverage, ...] = ()

    @property
    def present_icons(self) -> tuple[IconCoverage, ...]:
        return tuple(coverage for coverage in self.icon_coverage if coverage.is_present)

    @property
    def missing_icons(self) -> tuple[IconCoverage, ...]:
        return tuple(coverage for coverage in self.icon_coverage if not coverage.is_present)

    @property
    def occupied_reserved_codepoints(self) -> tuple[IconCoverage, ...]:
        return tuple(coverage for coverage in self.reserved_coverage if coverage.is_present)


def inspect_agent_font(path: Path, manifest: Manifest | None = None) -> FontInspection:
    loaded_manifest = manifest or load_manifest()
    candidate = inspect_font(path)
    codepoint_result = read_font_codepoints(path)
    available_icons = tuple(icon for icon in loaded_manifest.icons if icon.asset_status == "available")
    reserved_icons = tuple(
        icon for icon in loaded_manifest.icons if icon.asset_status in {"reserved", "deprecated"}
    )
    icon_coverage = tuple(
        IconCoverage(
            icon=icon,
            is_present=codepoint_to_int(icon.codepoint) in codepoint_result.codepoints,
        )
        for icon in available_icons
    )
    reserved_coverage = tuple(
        IconCoverage(
            icon=icon,
            is_present=codepoint_to_int(icon.codepoint) in codepoint_result.codepoints,
        )
        for icon in reserved_icons
    )
    return FontInspection(
        candidate=candidate,
        manifest=loaded_manifest,
        icon_coverage=icon_coverage,
        codepoints_error=codepoint_result.error,
        reserved_coverage=reserved_coverage,
    )
