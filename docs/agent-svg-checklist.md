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
| 1 | Claude Code | `claude-code` | `U+100041` | SVGL has Claude AI; verify Claude Code-specific use. | missing |
| 2 | Codex | `codex` | `U+100040` | SVGL has Codex. | missing |
| 3 | Grok | `grok` | `U+100051` | SVGL has Grok and xAI/Grok. | missing |
| 4 | Gemini | `gemini-cli` | `U+100044` | SVGL has Gemini. | missing |
| 5 | Antigravity | `antigravity` | `U+10004C` | SVGL has Google Antigravity. | missing |
| 6 | Pi | `pi` | `U+100052` | Needs product-specific source; SVGL Raspberry Pi is a false positive. | missing |
| 7 | Hermes Agent | `hermes-agent` | `U+100045` | Needs upstream source. | missing |
| 8 | OpenCode | `opencode` | `U+100043` | SVGL has OpenCode. | missing |
| 9 | Goose | `goose` | `U+100053` | Needs upstream source. | missing |
| 10 | Amp | `amp` | `U+100046` | Needs Sourcegraph Amp source; SVGL AMP is a false positive. | missing |
| 11 | Auggie | `auggie` | `U+10004D` | Needs Augment/Auggie source. | missing |
| 12 | Autohand Code | `autohand-code` | `U+100054` | Needs upstream source. | missing |
| 13 | Charm | `charm` | `U+100047` | Needs product-specific source; SVGL PyCharm is a false positive. | missing |
| 14 | Cline | `cline` | `U+10004E` | Needs upstream source. | missing |
| 15 | Codebuff | `codebuff` | `U+100055` | Needs upstream source. | missing |
| 16 | Continue | `continue` | `U+100048` | Needs upstream source. | missing |
| 17 | Cursor | `cursor` | `U+100042` | SVGL has Cursor and a Cursor brand URL. | missing |
| 18 | Droid | `droid` | `U+100056` | Needs product-specific source; SVGL Android is a false positive. | missing |
| 19 | GitHub Copilot | `github-copilot` | `U+100049` | SVGL has GitHub Copilot; Octicons/Codicons may have related glyphs. | missing |
| 20 | Kilocode | `kilocode` | `U+10004F` | SVGL has Kilocode. | missing |
| 21 | Kimi | `kimi` | `U+100057` | SVGL has Kimi. | missing |
| 22 | Kiro | `kiro` | `U+10004A` | Needs upstream source. | missing |
| 23 | Mistral Vibe | `mistral-vibe` | `U+100050` | SVGL has Mistral AI; verify Vibe-specific use. | missing |
| 24 | Qwen Code | `qwen-code` | `U+100058` | SVGL has Qwen; verify Qwen Code-specific use. | missing |
| 25 | Rovo Dev | `rovo-dev` | `U+10004B` | Needs Atlassian/Rovo Dev source. | missing |
| 26 | Orca ADE | `orca-ade` | `U+100059` | Official site exposes `/logo.svg`; GitHub repo is MIT. | missing |

## First Import Batch

Start with entries that already have SVGL or official SVG leads:

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
