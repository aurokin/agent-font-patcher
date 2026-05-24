# Brainstorm: Agent Tool Glyphs for Nerd Fonts

## Product Shape

This should feel like a focused Nerd Fonts add-on, not a general icon font. The
value is that agent-related terminal tools can render compact status indicators,
model/provider labels, and command prompts without shipping custom assets.

Possible package outputs:

- `AgentSymbols.ttf`: standalone symbol font.
- `AgentSymbolsNerdFont-Regular.ttf`: patched common base font.
- `glyphnames.json`: machine-readable names, aliases, and codepoints.
- `agent-symbols.css`: optional web preview support.
- `specimen.html` and `specimen.png`: review artifacts.

## Core Constraints

- Use the Private Use Area to avoid pretending these are Unicode-standard icons.
- Avoid collisions with Nerd Fonts by documenting the exact allocation range.
- Prefer outline simplification over literal logos when marks fail at terminal
  sizes.
- Keep every glyph legally traceable to a source and license.
- Make the build reproducible from clean source assets.

## Candidate Codepoint Strategy

Use a dedicated range under Supplementary Private Use Area-A for the project
metadata, while optionally supporting a Basic Multilingual Plane compatibility
range if terminal support requires it.

Initial practical option:

- Primary range: `U+F5000` onward if compatible with existing font workflows.
- Reserve blocks by category:
  - `F5000-F50FF`: providers and labs
  - `F5100-F51FF`: coding agents and IDE assistants
  - `F5200-F52FF`: orchestration protocols and frameworks
  - `F5300-F53FF`: local model runtimes

Before committing to this range, compare against current Nerd Fonts allocations.

## Candidate Glyphs

Provider/lab marks:

- Anthropic / Claude
- OpenAI
- Google Gemini
- GitHub Copilot
- Perplexity
- Mistral
- Meta AI / Llama

Coding agents and IDE assistants:

- Codex
- Cursor
- Aider
- Continue
- Sourcegraph Cody
- Goose
- Devin
- Windsurf

Protocols, frameworks, and infrastructure:

- MCP
- LangChain
- LlamaIndex
- CrewAI
- AutoGen
- Ollama
- LM Studio
- vLLM

Terminal status concepts that may need original glyphs:

- Agent active
- Agent paused
- Tool call running
- Tool call failed
- Context compacted
- Approval required
- Sandbox locked
- Browser controlled
- Local model
- Remote model

## Legal / Licensing Questions

- Which marks can be redistributed inside a patched font?
- Which marks can only be documented as user-supplied assets?
- Do project names need attribution in generated font metadata?
- Should the repo ship only conversion recipes and metadata for restricted marks?

Conservative default: do not commit brand SVGs until license review is complete.

## Technical Questions

- Should this wrap upstream Nerd Fonts patcher or use `fonttools` directly?
- Which base fonts should be first-class test targets?
- Can SVG normalization be deterministic across macOS and Linux?
- How much hinting survives glyph insertion?
- What is the minimum terminal matrix for QA?

## MVP

1. Define metadata schema for glyphs.
2. Add three original/non-branded status glyphs.
3. Patch one permissive base font.
4. Generate an HTML specimen. Add PNG snapshots once a renderer dependency is
   chosen.
5. Document how brand glyphs will be added after licensing review.

## Risks

- Trademark or redistribution limits for brand marks.
- Poor legibility when color logos are flattened into monochrome glyphs.
- Codepoint collisions with user fonts or upstream Nerd Fonts.
- Fragile build tooling around font metrics and hinting.
