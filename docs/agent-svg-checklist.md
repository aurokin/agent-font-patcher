# Agent SVG Checklist

This is the acquisition checklist for the first branded agent SVG batch. Keep
this list in sync with `src/agent_font_patcher/data/codepoints.json`.

## Asset Convention

- Normalized assets live under `src/agent_font_patcher/data/assets/agents/`.
- File names use the stable manifest ID, for example `codex.svg`.
- SVGs must be path-only, monochrome, and accepted by the patcher.
- Manifest entries move from `reserved` to `available` only after the asset is
  checked in with source, license/policy, and attribution metadata.
- Including a logo does not grant downstream users trademark, brand, or logo
  usage rights.

## Target List

| Order | Agent | Manifest ID | Codepoint | Source lead | Asset |
| --- | --- | --- | --- | --- | --- |
| 1 | Claude Code | `claude-code` | `U+100041` | SVGL has Claude AI; using Claude AI mark for Claude Code. | available: `src/agent_font_patcher/data/assets/agents/claude-code.svg` |
| 2 | Codex | `codex` | `U+100040` | SVGL has Codex. | available: `src/agent_font_patcher/data/assets/agents/codex.svg` |
| 3 | Grok | `grok` | `U+100051` | SVGL has Grok and xAI/Grok. | available: `src/agent_font_patcher/data/assets/agents/grok.svg` |
| 4 | Gemini | `gemini-cli` | `U+100044` | SVGL has Gemini. | available: `src/agent_font_patcher/data/assets/agents/gemini-cli.svg` |
| 5 | Antigravity | `antigravity` | `U+10004C` | SVGL has Google Antigravity. | available: `src/agent_font_patcher/data/assets/agents/antigravity.svg` |
| 6 | Pi | `pi` | `U+100052` | No product-specific SVG found; Inflection AI logo is parent-brand fallback; Raspberry Pi and `pi-mono` are false positives. | missing |
| 7 | Hermes Agent | `hermes-agent` | `U+100045` | Official OSS repo has `acp_registry/icon.svg`. | available: `src/agent_font_patcher/data/assets/agents/hermes-agent.svg` |
| 8 | OpenCode | `opencode` | `U+100043` | SVGL has OpenCode. | available: `src/agent_font_patcher/data/assets/agents/opencode.svg` |
| 9 | Goose | `goose` | `U+100053` | Official OSS repo has `ui/desktop/src/images/glyph.svg`. | available: `src/agent_font_patcher/data/assets/agents/goose.svg` |
| 10 | Amp | `amp` | `U+100046` | Product-specific source: `https://ampcode.com/amp-mark-color.svg`; SVGL AMP is a false positive. | available: `src/agent_font_patcher/data/assets/agents/amp.svg` |
| 11 | Auggie | `auggie` | `U+10004D` | Official Augment site exposes brand SVGs; no Auggie-specific OSS SVG found. | missing |
| 12 | Autohand Code | `autohand-code` | `U+100054` | Deferred: official repo has PNG/favicon assets, but no product SVG. | missing |
| 13 | Charm | `charm` | `U+100047` | Deferred: product-specific Crush lead is PNG-only. | missing |
| 14 | Cline | `cline` | `U+10004E` | Official brand page has bot SVG; OSS repo also has `assets/icons/icon.svg`. | available: `src/agent_font_patcher/data/assets/agents/cline.svg` |
| 15 | Codebuff | `codebuff` | `U+100055` | Deferred: official repo has PNG logo assets, but no SVG. | missing |
| 16 | Continue | `continue` | `U+100048` | Official OSS repo has `docs/logo/dark.svg`. | available: `src/agent_font_patcher/data/assets/agents/continue.svg` |
| 17 | Cursor | `cursor` | `U+100042` | SVGL has Cursor and a Cursor brand URL. | available: `src/agent_font_patcher/data/assets/agents/cursor.svg` |
| 18 | Droid | `droid` | `U+100056` | Needs product-specific source; Factory brand SVG exists, but Droid assets found are PNG/GIF. | missing |
| 19 | GitHub Copilot | `github-copilot` | `U+100049` | SVGL has GitHub Copilot; Octicons/Codicons may have related glyphs. | available: `src/agent_font_patcher/data/assets/agents/github-copilot.svg` |
| 20 | Kilocode | `kilocode` | `U+10004F` | SVGL has Kilocode. | available: `src/agent_font_patcher/data/assets/agents/kilocode.svg` |
| 21 | Kimi | `kimi` | `U+100057` | SVGL has Kimi. | available: `src/agent_font_patcher/data/assets/agents/kimi.svg` |
| 22 | Kiro | `kiro` | `U+10004A` | Official site exposes `https://kiro.dev/icon.svg`. | available: `src/agent_font_patcher/data/assets/agents/kiro.svg` |
| 23 | Mistral Vibe | `mistral-vibe` | `U+100050` | SVGL has Mistral AI; using Mistral AI mark for Mistral Vibe. | available: `src/agent_font_patcher/data/assets/agents/mistral-vibe.svg` |
| 24 | Qwen Code | `qwen-code` | `U+100058` | SVGL has Qwen; verify Qwen Code-specific use. | available: `src/agent_font_patcher/data/assets/agents/qwen-code.svg` |
| 25 | Rovo Dev | `rovo-dev` | `U+10004B` | Atlassian logo zip contains `rovo/SVG/Rovo_icon.svg`. | available: `src/agent_font_patcher/data/assets/agents/rovo-dev.svg` |
| 26 | Orca ADE | `orca-ade` | `U+100059` | Official site exposes `/logo.svg`; GitHub repo is MIT. | available: `src/agent_font_patcher/data/assets/agents/orca-ade.svg` |

## Imported Assets

These entries now have normalized SVG assets:

- `codex`
- `opencode`
- `cursor`
- `kilocode`
- `kimi`
- `qwen-code`
- `grok`
- `antigravity`
- `github-copilot`
- `gemini-cli`
- `orca-ade`
- `claude-code`
- `mistral-vibe`
- `hermes-agent`
- `goose`
- `amp`
- `cline`
- `continue`
- `kiro`
- `rovo-dev`

## Deferred Candidates

These stay reserved in the active manifest but are deferred for asset import:

- `autohand-code`: official repo has PNG/favicon assets, but no product SVG.
- `charm`: product-specific Crush lead is PNG-only.
- `codebuff`: official repo has PNG logo assets, but no SVG.
