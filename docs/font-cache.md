# Font Cache Handling

Font cache refresh is part of the in-place patching experience. If a font file
is modified but the operating system or terminal keeps using a cached face,
users will think the patch failed.

Cache refresh should be platform-aware, conservative, and batched. For
`--all-detected --in-place`, patch all writable fonts first, then refresh caches
once.

## Defaults

Branch-off mode:

- do not refresh caches automatically unless the tool also installs the output
  into a known font directory;
- print the output path and tell the user to select the new family.

In-place mode:

- refresh user-level font caches after successful patching by default;
- offer `--no-refresh-cache`;
- always tell users to restart affected terminal apps if old glyphs still render.

## macOS

Expected user-level refresh sequence:

```bash
atsutil databases -removeUser
atsutil server -shutdown
atsutil server -ping
```

Implementation notes:

- Prefer user-level cache removal over system-wide cache removal.
- Do not require elevated permissions for normal user font directories.
- If the target is not writable, fail before cache work.
- If a font lives in a Homebrew-managed location and is writable, allow in-place
  patching because the user can reinstall the package to restore the original.
- Print a clear restart hint for Terminal, iTerm2, Ghostty, WezTerm, Kitty, and
  other running terminal apps.

Open question: whether macOS cache refresh should be automatic for every
in-place run or gated behind `--refresh-cache` until tested across terminal apps.

## Linux

Expected refresh command:

```bash
fc-cache -f
```

When possible, scope to the relevant font directory:

```bash
fc-cache -f ~/.local/share/fonts
```

Implementation notes:

- Detect whether `fc-cache` exists before attempting refresh.
- Prefer scoped refresh when all patched fonts are under the same known font
  directory.
- Fall back to a general `fc-cache -f` when scope is mixed or unclear.

## Windows

Initial support should avoid aggressive cache manipulation.

Implementation notes:

- Support outputting or patching font files first.
- Provide manual reinstall/restart guidance.
- Defer service-level cache reset automation until tested on Windows.

## CLI Shape

Expose cache operations directly:

```text
agent-font-patcher cache refresh
agent-font-patcher cache refresh --user
agent-font-patcher cache refresh --system
```

Patch operations can call cache refresh internally:

```text
agent-font-patcher patch --in-place --refresh-cache <font-path>
agent-font-patcher patch --in-place --no-refresh-cache <font-path>
```

`--system` should never be implied by default.

