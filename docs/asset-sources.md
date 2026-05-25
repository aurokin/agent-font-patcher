# Asset Sources

This project can reserve glyph codepoints before it ships a logo. Reserved
entries stay `asset_status=reserved` until the SVG is source-traced,
normalized, and checked in with source, license/policy, and attribution
metadata.

Bundling a third-party logo in this font does not grant trademark, brand, or
other usage rights to downstream users. Projects using the font are responsible
for making sure their own use of any logo is allowed. Removal requests should be
opened as GitHub issues.

## SVGL

Primary upstream reference:

- <https://github.com/pheralb/svgl>
- <https://svgl.app/>

SVGL is useful for discovery because it indexes current product logos and
exposes API/repository metadata. This project follows the same practical
posture: include source links and attribution, do not claim logo rights for
users, and remove disputed assets through GitHub issues.

Use this policy for SVGL-derived candidates:

> Each SVG includes a link to its respective product. Permission must be
> obtained before using a logo. For removal requests, please open an issue on
> GitHub.

The SVGL repository also asks contributors to ensure they have the right to use
an SVG and that its license permits adding it to SVGL. Treat that as a source
quality signal, not as a trademark grant to downstream font users.

Before an SVGL-derived glyph becomes `available`:

- identify the product's own brand/logo terms or upstream license when
  available;
- record the product URL and, when available, brand guideline URL;
- commit a normalized path-only monochrome SVG that passes the patcher;
- add manifest `source`, `license`, and `attribution` fields;
- keep the original SVGL route in review notes when SVGL was used to find it.

## Requested Agent Coverage

These codepoints are reserved in `agent-icons-v2`. Availability means "found in
SVGL or official upstream during initial analysis", not that downstream users
receive rights to use that logo.

The exact import checklist, in screenshot order, lives in
[agent-svg-checklist.md](agent-svg-checklist.md).

| ID | Display name | Codepoint | Initial source lead | Status |
| --- | --- | --- | --- | --- |
| `claude-code` | Claude Code | `U+100041` | SVGL has Claude AI; verify Claude Code-specific use. | reserved |
| `codex` | Codex | `U+100040` | SVGL has Codex. | reserved |
| `grok` | Grok | `U+100051` | SVGL has Grok and xAI/Grok. | reserved |
| `gemini-cli` | Gemini | `U+100044` | SVGL has Gemini. | reserved |
| `antigravity` | Antigravity | `U+10004C` | SVGL has Google Antigravity. | reserved |
| `pi` | Pi | `U+100052` | Needs product-specific source; SVGL Raspberry Pi is a false positive. | reserved |
| `hermes-agent` | Hermes Agent | `U+100045` | Needs upstream source. | reserved |
| `opencode` | OpenCode | `U+100043` | SVGL has OpenCode. | reserved |
| `goose` | Goose | `U+100053` | Needs upstream source. | reserved |
| `amp` | Amp | `U+100046` | Needs Sourcegraph Amp source; SVGL AMP is a false positive. | reserved |
| `auggie` | Auggie | `U+10004D` | Needs Augment/Auggie source. | reserved |
| `autohand-code` | Autohand Code | `U+100054` | Needs upstream source. | reserved |
| `charm` | Charm | `U+100047` | Needs product-specific source; SVGL PyCharm is a false positive. | reserved |
| `cline` | Cline | `U+10004E` | Needs upstream source. | reserved |
| `codebuff` | Codebuff | `U+100055` | Needs upstream source. | reserved |
| `continue` | Continue | `U+100048` | Needs upstream source. | reserved |
| `cursor` | Cursor | `U+100042` | SVGL has Cursor and a Cursor brand URL. | reserved |
| `droid` | Droid | `U+100056` | Needs product-specific source; SVGL Android is a false positive. | reserved |
| `github-copilot` | GitHub Copilot | `U+100049` | SVGL has GitHub Copilot. Octicons/Codicons may also have related glyphs. | reserved |
| `kilocode` | Kilocode | `U+10004F` | SVGL has Kilocode. | reserved |
| `kimi` | Kimi | `U+100057` | SVGL has Kimi. | reserved |
| `kiro` | Kiro | `U+10004A` | Needs upstream source. | reserved |
| `mistral-vibe` | Mistral Vibe | `U+100050` | SVGL has Mistral AI; verify Vibe-specific use. | reserved |
| `qwen-code` | Qwen Code | `U+100058` | SVGL has Qwen; verify Qwen Code-specific use. | reserved |
| `rovo-dev` | Rovo Dev | `U+10004B` | Needs Atlassian/Rovo Dev source. | reserved |
| `orca-ade` | Orca ADE | `U+100059` | Official site exposes `/logo.svg`; GitHub repo is MIT. Verify logo terms. | reserved |

## Nerd Fonts Overlap

Nerd Fonts already aggregates generic icon families such as Codicons, Octicons,
Font Awesome, Material Design Icons, Devicons, Font Logos, and Powerline symbols.
Those are useful for generic status glyphs or fallback shapes, but they do not
cover the agent-specific brand list above as stable project-level codepoints.
