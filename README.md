# Agent Font Patcher

Patch Nerd Fonts-compatible fonts with glyphs for modern agent tooling.

This repository is starting as a design and tooling sandbox. The goal is to
define a repeatable CLI for taking approved monochrome/vector agent-tool marks,
assigning them to a private-use Unicode range, patching one or more base fonts,
and validating that the generated font renders cleanly in terminal UIs.

## Early Scope

- Build on Nerd Fonts conventions instead of replacing Nerd Fonts.
- Target terminal-friendly glyphs: single-color, recognizable at 12-18 px, and
  aligned to existing Nerd Fonts metrics.
- Keep icon metadata explicit: source, license, display name, preferred aliases,
  and assigned codepoint.
- Start with a small curated set, then expand once the pipeline is stable.

## Candidate Agent Tools

The first pass should consider tools and ecosystems commonly shown in developer
terminals:

- Claude / Anthropic
- OpenAI / ChatGPT / Codex
- Cursor
- GitHub Copilot
- Gemini
- Aider
- Continue
- Sourcegraph Cody
- Goose
- Devin
- MCP
- LangChain
- LlamaIndex
- Ollama
- LM Studio

Final inclusion depends on licensing, icon quality at small sizes, and whether a
glyph can be made legible without color.

## Proposed Pipeline

1. Collect source SVGs and license metadata.
2. Normalize each mark into monochrome SVG.
3. Convert SVG outlines into font glyphs.
4. Patch target fonts using stable private-use codepoints.
5. Embed patch metadata for later inspection.
6. Refresh font caches when in-place patching requires it.
7. Generate a glyph specimen sheet for visual QA.
8. Run font validation checks.

## Product Decisions

The project is focused on optional user-run font patching. Apps that can render
SVGs should use SVGs directly, while terminal apps can keep emoji or stock Nerd
Fonts fallbacks and use this project for accurate opt-in glyphs.

Supported output modes:

- Branch-off font: create a new `Agent Nerd Font` family. This is the default.
- In-place patch: mutate the selected installed font with backup and cache
  refresh support.

More detail lives in:

- [docs/decisions.md](docs/decisions.md)
- [docs/font-cache.md](docs/font-cache.md)
- [docs/brainstorm.md](docs/brainstorm.md)

## Current Status

- Git repository initialized.
- Product decisions captured in [docs/decisions.md](docs/decisions.md).
- Font cache strategy captured in [docs/font-cache.md](docs/font-cache.md).
- The referenced Claude share was loaded through Chrome and summarized in
  [docs/references/claude-share.md](docs/references/claude-share.md).
