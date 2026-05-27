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

These codepoints are reserved in `agent-icons-v6`. Availability means "found in
SVGL or official upstream during initial analysis", not that downstream users
receive rights to use that logo.

## Provider Coverage

| ID | Display name | Codepoint | Source lead | Status |
| --- | --- | --- | --- | --- |
| `anthropic` | Anthropic | `U+100000` | SVGL has Anthropic. | available |
| `openai` | OpenAI | `U+100001` | SVGL has OpenAI and OpenAI brand URL. | available |
| `gemini` | Gemini | `U+100002` | SVGL has Gemini. | available |

## Protocol Coverage

| ID | Display name | Codepoint | Source lead | Status |
| --- | --- | --- | --- | --- |
| `mcp` | MCP | `U+100080` | SVGL has Model Context Protocol at `model-context-protocol-light.svg`. | available |
| `agent-active` | Agent Active | `U+1000C0` | Custom status glyph needed. | reserved |
| `tool-call` | Tool Call | `U+1000C1` | Custom tool-call glyph needed. | reserved |

The exact import checklist, in screenshot order, lives in
[agent-svg-checklist.md](agent-svg-checklist.md).

| ID | Display name | Codepoint | Initial source lead | Status |
| --- | --- | --- | --- | --- |
| `claude-code` | Claude Code | `U+100041` | SVGL has Claude AI; using Claude AI mark for Claude Code. | available |
| `codex` | Codex | `U+100040` | SVGL has Codex. | available |
| `grok` | Grok | `U+100051` | SVGL has Grok and xAI/Grok. | available |
| `gemini-cli` | Gemini | `U+100044` | SVGL has Gemini. | available |
| `antigravity` | Antigravity | `U+10004C` | SVGL has Google Antigravity. | available |
| `pi` | Pi | `U+100052` | Homarr dashboard-icons has `pi-coding-agent.svg`. | available |
| `hermes-agent` | Hermes Agent | `U+100045` | Official OSS repo has `acp_registry/icon.svg`. | available |
| `opencode` | OpenCode | `U+100043` | SVGL has OpenCode. | available |
| `goose` | Goose | `U+100053` | Official OSS repo has `ui/desktop/src/images/glyph.svg`. | available |
| `amp` | Amp | `U+100046` | Product-specific source: `https://ampcode.com/amp-mark-color.svg`; SVGL AMP is a false positive. | available |
| `auggie` | Auggie | `U+10004D` | Coder registry module exposes `auggie.svg`. | available |
| `autohand-code` | Autohand Code | `U+100054` | Official Autohand site exposes light/dark SVG logos. | available |
| `charm` | Charm | `U+100047` | Deferred: product-specific Crush lead is PNG-only. | reserved |
| `cline` | Cline | `U+10004E` | Official brand page has bot SVG; OSS repo also has `assets/icons/icon.svg`. | available |
| `codebuff` | Codebuff | `U+100055` | Deferred: official repo has PNG logo assets, but no SVG. | reserved |
| `continue` | Continue | `U+100048` | Official OSS repo has `docs/logo/dark.svg`. | available |
| `cursor` | Cursor | `U+100042` | SVGL has Cursor and a Cursor brand URL. | available |
| `droid` | Droid | `U+100056` | Agent Client Protocol registry docs include a Factory Droid SVG. | available |
| `github-copilot` | GitHub Copilot | `U+100049` | SVGL has GitHub Copilot. Octicons/Codicons may also have related glyphs. | available |
| `kilocode` | Kilocode | `U+10004F` | SVGL has Kilocode. | available |
| `kimi` | Kimi | `U+100057` | SVGL has Kimi. | available |
| `kiro` | Kiro | `U+10004A` | Official site exposes `https://kiro.dev/icon.svg`. | available |
| `mistral-vibe` | Mistral Vibe | `U+100050` | SVGL has Mistral AI; using Mistral AI mark for Mistral Vibe. | available |
| `qwen-code` | Qwen Code | `U+100058` | SVGL has Qwen; verify Qwen Code-specific use. | available |
| `rovo-dev` | Rovo Dev | `U+10004B` | Atlassian logo zip contains `rovo/SVG/Rovo_icon.svg`. | available |
| `orca-ade` | Orca ADE | `U+100059` | Official site exposes `/logo.svg`; GitHub repo is MIT. Verify logo terms. | available |

## Nerd Fonts Overlap

Nerd Fonts already aggregates generic icon families such as Codicons, Octicons,
Font Awesome, Material Design Icons, Devicons, Font Logos, and Powerline symbols.
Those are useful for generic status glyphs or fallback shapes, but they do not
cover the agent-specific brand list above as stable project-level codepoints.

## Deferred Candidates

These candidates stay reserved in the active manifest but are deferred for asset import:

- `charm`: product-specific Crush lead is PNG-only.
- `codebuff`: official repo has PNG logo assets, but no SVG.
