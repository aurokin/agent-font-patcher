# Product Decisions

This project is focused only on font patching. Apps that can render SVGs should
use SVGs directly; this tool exists for terminal surfaces where the only portable
rendering primitive is a font glyph.

## Direction

Build an optional user-run CLI that adds an agent icon layer to existing Nerd
Fonts-compatible fonts.

The CLI should not be required for a terminal app to work. Terminal apps should
keep emoji or stock Nerd Fonts fallbacks, while users who want accurate agent
icons can patch their own installed fonts.

## Output Modes

The patch operation has two supported output modes.

### Branch-Off Font

Create a new font file and a new family/name.

Example:

```text
JetBrainsMono Nerd Font.ttf
-> JetBrainsMono Agent Nerd Font.ttf
```

This is the safest default because it does not mutate package-managed font
files. The tradeoff is that users must update their terminal configuration to
select the new family.

Branch-off mode should:

- write to an explicit output directory;
- rename font family metadata to include an `Agent` marker;
- preserve the source file untouched;
- work without elevated permissions;
- be the default mode for `patch`.

### In-Place Patch

Modify an existing font file directly.

This is useful for users who install fonts through a package manager such as
Homebrew and are comfortable restoring the original by reinstalling the package.
It also avoids changing terminal profile configuration.

In-place mode should:

- require an explicit `--in-place` flag;
- create a backup by default;
- offer `--no-backup` only as an explicit escape hatch;
- preserve the original family/name metadata;
- embed patch metadata so `inspect` can identify the applied manifest;
- refresh font caches after a successful batch unless disabled.

## CLI Surface

Initial commands:

```text
agent-font-patcher scan
agent-font-patcher patch <font-path>
agent-font-patcher patch --in-place <font-path>
agent-font-patcher inspect <font-path>
agent-font-patcher restore <font-path>
agent-font-patcher cache refresh
agent-font-patcher preview <font-path>
```

`scan` should be conservative. It should report likely Nerd Fonts, their paths,
whether they appear writable, and whether they already contain this project's
agent glyph metadata.

The first scanner implementation is read-only. It searches common platform font
directories and uses font metadata to identify likely Nerd Fonts. It should
prefer false negatives over accidentally treating unrelated fonts as patch
targets.

The first release patches one explicit font path per invocation. Batch patching
can be added later, but should still patch every file first and refresh font
caches once at the end.

`inspect` should read embedded metadata and report:

- whether the font is patched;
- manifest version;
- patcher version;
- source font name and source hash when available;
- icon count and codepoint range.

`restore` should restore from backups created by in-place patching.

## Embedded Metadata

Every patched font should include project metadata. The exact table/field format
is still open, but the data model should include:

```json
{
  "project": "agent-font-patcher",
  "patcher_version": "0.1.0",
  "manifest_version": "agent-icons-v8",
  "codepoint_range": "U+100000-U+1000FF",
  "source_font_name": "JetBrainsMono Nerd Font Regular",
  "source_font_hash": "sha256:...",
  "patched_at": "2026-05-23T00:00:00Z"
}
```

This metadata matters most for in-place patching because users may forget which
fonts they modified.

## Codepoint Manifest

The project should publish a stable `codepoints.json` manifest. Apps should read
or vendor the manifest rather than hardcoding codepoints independently.

The manifest should map stable icon IDs to:

- codepoint;
- display name;
- aliases;
- category;
- source asset;
- source license and attribution;
- optional upstream-equivalent codepoint when Nerd Fonts later adds the icon.

The first public range is `U+100000-U+1000FF` in Supplementary Private Use
Area-B. The current packaged manifest is `agent-icons-v8`.

## Non-Goals

- Do not replace Nerd Fonts.
- Do not require patched fonts for terminal apps to function.
- Do not make this project the rendering path for GUI apps that can use SVG.
- Do not silently mutate package-managed fonts without an explicit in-place
  request.
