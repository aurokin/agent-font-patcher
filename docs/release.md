# Release Checklist

Use this checklist before tagging a public release.

## Local Checks

```bash
uv run --locked ruff check .
uv run --locked python -m pytest -q
uv build
```

After `uv build`, inspect the generated artifacts:

```bash
python -m tarfile -l dist/agent_font_patcher-*.tar.gz | sort
python -m zipfile -l dist/agent_font_patcher-*.whl | sort
```

Confirm the wheel includes:

- `agent_font_patcher/data/codepoints.json`
- all `agent_font_patcher/data/assets/agents/*.svg` assets
- `agent_font_patcher-*.dist-info/licenses/LICENSE`
- `agent_font_patcher-*.dist-info/licenses/NOTICE.md`
- `agent_font_patcher-*.dist-info/licenses/LICENSES/Apache-2.0.txt`
- `agent_font_patcher-*.dist-info/licenses/LICENSES/CC-BY-4.0.txt`

## Functional Smoke

Run against a real Nerd Font before release:

```bash
agent-font-patcher patch "/path/to/ExampleNerdFont-Regular.ttf" --output-dir ./out
agent-font-patcher inspect ./out/ExampleNerdFont-Regular-Agent.ttf
agent-font-patcher preview ./out/ExampleNerdFont-Regular-Agent.ttf --output-dir ./out
```

Expected `agent-icons-v8` smoke result:

- patch output includes `patched_codepoints: 32`
- inspect output includes `available_agent_glyphs: 32/32 present`
- preview output includes `agent_glyphs: 32/32 present`

## Platform Smoke

- macOS branch-off patch.
- macOS in-place patch with backup, restore, and cache refresh.
- Linux branch-off patch.
- Linux `cache refresh` with `fc-cache`.

Windows cache refresh currently reports restart guidance instead of resetting
font cache services.

## Release Notes

Record:

- package version;
- manifest version;
- number of packaged glyphs;
- any codepoint additions, removals, or deprecations;
- attribution or license changes.
