from __future__ import annotations

import base64
import html
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_font_patcher.inspector import FontInspection, IconCoverage, inspect_agent_font
from agent_font_patcher.manifest import Manifest, codepoint_to_int, load_manifest


class SpecimenError(ValueError):
    """Raised when a specimen cannot be generated."""


@dataclass(frozen=True)
class SpecimenResult:
    font_path: Path
    output_path: Path
    present_count: int
    total_count: int
    patch_metadata: dict[str, Any] | None


def generate_html_specimen(
    font_path: Path,
    output_path: Path,
    manifest: Manifest | None = None,
) -> SpecimenResult:
    if font_path.suffix.lower() in {".ttc", ".otc"}:
        raise SpecimenError("preview does not support font collections yet")
    loaded_manifest = manifest or load_manifest()
    try:
        font_data = font_path.read_bytes()
    except OSError as error:
        raise SpecimenError(f"unable to read font for specimen: {error}") from error
    if font_data.startswith(b"ttcf"):
        raise SpecimenError("preview does not support font collections yet")

    inspection = inspect_agent_font(font_path, loaded_manifest)
    if inspection.codepoints_error:
        raise SpecimenError(f"unable to inspect font codepoints: {inspection.codepoints_error}")

    html_text = _render_specimen_html(inspection, font_data)
    try:
        _write_specimen_exclusive(output_path, html_text, font_path)
    except OSError as error:
        raise SpecimenError(f"unable to write specimen: {error}") from error
    coverage = _specimen_coverage(inspection)
    return SpecimenResult(
        font_path=font_path,
        output_path=output_path,
        present_count=sum(1 for item in coverage if item.is_present),
        total_count=len(coverage),
        patch_metadata=inspection.patch_metadata,
    )


def default_specimen_path(font_path: Path, output_dir: Path | None = None) -> Path:
    directory = output_dir or font_path.parent
    return directory / f"{font_path.stem}-agent-specimen.html"


def _write_specimen_exclusive(output_path: Path, html_text: str, font_path: Path) -> None:
    if output_path.is_symlink():
        raise SpecimenError(f"specimen output must not be a symlink: {output_path}")
    if output_path.exists():
        try:
            if output_path.samefile(font_path):
                raise SpecimenError("specimen output must not overwrite the source font")
        except OSError:
            pass
        raise SpecimenError(f"specimen output already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    temp_file = tempfile.NamedTemporaryFile(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        mode="w",
        encoding="utf-8",
        delete=False,
    )
    try:
        temp_path = Path(temp_file.name)
        with temp_file:
            temp_file.write(html_text)
        os.link(temp_path, output_path)
    except FileExistsError as error:
        raise SpecimenError(f"specimen output already exists: {output_path}") from error
    finally:
        if not temp_file.file.closed:
            temp_file.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _render_specimen_html(inspection: FontInspection, font_data: bytes) -> str:
    candidate = inspection.candidate
    title = f"{candidate.full_name or candidate.family or candidate.path.stem} Agent Glyph Specimen"
    font_mime = _font_mime(candidate.path)
    font_format = _font_format(candidate.path)
    font_base64 = base64.b64encode(font_data).decode("ascii")
    rows = "\n".join(_render_icon_card(coverage) for coverage in _specimen_coverage(inspection))
    metadata = inspection.patch_metadata or {}
    metadata_rows = "\n".join(
        _definition_row(label, value)
        for label, value in (
            ("Font", candidate.full_name or candidate.family or candidate.path.stem),
            ("Family", candidate.family or "unknown"),
            ("Manifest", inspection.manifest.manifest_version),
            ("Patched", "yes" if inspection.patch_metadata else "no"),
            ("Patch manifest", metadata.get("manifest_version", "unknown")),
            ("Patched icons", str(len(metadata.get("patched_codepoints", [])))),
            ("Source hash", metadata.get("source_font_hash", "unknown")),
        )
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    @font-face {{
      font-family: "Agent Font Specimen";
      src: url("data:{font_mime};base64,{font_base64}") format("{font_format}");
    }}
    :root {{
      color-scheme: light dark;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    body {{
      margin: 0;
      padding: 32px;
      line-height: 1.45;
      background: Canvas;
      color: CanvasText;
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: 28px;
    }}
    .summary {{
      display: grid;
      grid-template-columns: max-content minmax(0, 1fr);
      gap: 6px 16px;
      margin: 0 0 28px;
      max-width: 920px;
    }}
    .summary dt {{
      font-weight: 700;
    }}
    .summary dd {{
      margin: 0;
      overflow-wrap: anywhere;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
      gap: 12px;
      max-width: 1120px;
    }}
    .card {{
      border: 1px solid color-mix(in srgb, CanvasText 18%, Canvas);
      border-radius: 6px;
      padding: 12px;
      min-width: 0;
    }}
    .glyph {{
      font-family: "Agent Font Specimen", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 36px;
      line-height: 1;
      width: 48px;
      height: 48px;
      display: inline-grid;
      place-items: center;
      border: 1px solid color-mix(in srgb, CanvasText 16%, Canvas);
      border-radius: 4px;
      margin-bottom: 10px;
    }}
    .missing .glyph {{
      opacity: 0.35;
    }}
    .name {{
      font-weight: 700;
      overflow-wrap: anywhere;
    }}
    .meta {{
      color: color-mix(in srgb, CanvasText 70%, Canvas);
      font-size: 13px;
    }}
    .status {{
      margin-top: 8px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0;
      font-weight: 700;
    }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <dl class="summary">
{metadata_rows}
  </dl>
  <section>
    <h2>Agent Glyphs</h2>
    <div class="grid">
{rows}
    </div>
  </section>
</body>
</html>
"""


def _specimen_coverage(inspection: FontInspection) -> tuple[IconCoverage, ...]:
    return tuple(
        sorted(
            (*inspection.icon_coverage, *inspection.reserved_coverage),
            key=lambda coverage: codepoint_to_int(coverage.icon.codepoint),
        )
    )


def _render_icon_card(coverage: Any) -> str:
    icon = coverage.icon
    status = "present" if coverage.is_present else "missing"
    codepoint_value = codepoint_to_int(icon.codepoint)
    return f"""      <article class="card {status}">
        <div class="glyph">&#x{codepoint_value:X};</div>
        <div class="name">{html.escape(icon.display_name)}</div>
        <div class="meta">{html.escape(icon.codepoint)} · {html.escape(icon.id)}</div>
        <div class="meta">{html.escape(icon.category)} · {html.escape(icon.asset_status)}</div>
        <div class="status">{status}</div>
      </article>"""


def _definition_row(label: str, value: object) -> str:
    return f"    <dt>{html.escape(label)}</dt><dd>{html.escape(str(value))}</dd>"


def _font_mime(path: Path) -> str:
    if path.suffix.lower() == ".otf":
        return "font/otf"
    return "font/ttf"


def _font_format(path: Path) -> str:
    if path.suffix.lower() == ".otf":
        return "opentype"
    return "truetype"
