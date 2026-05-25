# Codepoint Manifest

The project publishes a stable codepoint manifest so terminal apps and patched
fonts can agree on the same glyphs.

## Initial Range

Initial allocation uses Supplementary Private Use Area-B:

```text
U+100000-U+1000FF
```

Reasoning:

- Nerd Fonts primarily uses the Basic Multilingual Plane PUA and parts of
  Supplementary Private Use Area-A.
- A high PUA-B range is less likely to collide with existing Nerd Fonts glyphs.
- The range is large enough for the first public manifest while leaving room for
  category blocks.

Tradeoff: some older tools and config formats handle six-digit codepoints less
ergonomically than `U+Fxxx` values. If that becomes a practical issue, the
project can add a separately documented compatibility range later.

Reference:

- Nerd Fonts glyph allocation wiki:
  <https://github.com/ryanoasis/nerd-fonts/wiki/Glyph-Sets-and-Code-Points>

## Block Layout

```text
U+100000-U+10003F  Providers and labs
U+100040-U+10007F  Coding agents and IDE assistants
U+100080-U+1000BF  Protocols, frameworks, and infrastructure
U+1000C0-U+1000FF  Local runtimes and terminal status glyphs
```

The coding-agent block currently reserves entries for Claude Code, Codex, Grok,
Gemini, Antigravity, Pi, Hermes Agent, OpenCode, Goose, Amp, Auggie, Autohand
Code, Charm, Cline, Codebuff, Continue, Cursor, Droid, GitHub Copilot, Kilocode,
Kimi, Kiro, Mistral Vibe, Qwen Code, Rovo Dev, and Orca ADE.

## Manifest Rules

- Icon IDs are stable lowercase identifiers.
- Codepoints are uppercase `U+` strings.
- Once published, a codepoint should not be reassigned.
- Deprecated icons remain in the manifest with replacement metadata.
- Apps should read or vendor the manifest rather than hand-copying codepoints.
- If Nerd Fonts later adds an upstream equivalent, this manifest should record
  the upstream codepoint instead of breaking existing assignments.

## Asset Status

Manifest entries can reserve codepoints before a redistributable glyph asset is
available.

```text
reserved    Codepoint is allocated, but no glyph asset is shipped yet.
available   Glyph asset is shipped and includes source, license, and attribution.
deprecated  Codepoint remains reserved for compatibility but should not be used
            for new output.
```

Reserved entries prevent churn while the asset pipeline is still being built.
They must not be treated as proof that a glyph exists in a patched font.

Asset source and license analysis lives in [asset-sources.md](asset-sources.md).
