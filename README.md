# sm0l (Linux)

Tiny local coding + research agent. Linux dashboard, no heartbeat, user prompts only.

Short soul, eight tools, autocompaction against the selected model's native context window.

This is the Linux port of sm0l. Line endings are LF. Shell, paths, fonts, and install layout follow Linux / XDG conventions.


## What it is

A PyQt6 dashboard (Eche-purple) that talks to a local Ollama or LM Studio server:

- Chat, sessions, workspace picker
- Model list / pull from the UI (no CLI) — Ollama only; LM Studio models are downloaded from its own Discover tab or `lms get`
- DuckDuckGo search + page fetch
- Files + shell for coding on this machine
- Autocompact using the **same** model when the window fills

It will not ping you, cron itself, or invent a turn. You send a message or nothing happens.

## Requirements

- Linux (X11 or Wayland)
- Python 3.11+ (to build or run from source)
- [Ollama](https://ollama.com) **or** [LM Studio](https://lmstudio.ai) running locally (pick one in the Settings panel)
- A local chat model
- Qt runtime libs (pulled in by the `PyQt6` wheel for most distros)

On Debian/Ubuntu, install a venv-capable Python (required for `./run.sh`, `./build.sh`, and source `./install.sh`):

```bash
sudo apt install python3-venv python3-pip libxcb-cursor0 libxkbcommon-x11-0
```

## Paths

| What | Where |
|---|---|
| Config | `$XDG_CONFIG_HOME/sm0l/config.json` or `~/.config/sm0l/config.json` |
| Sessions / app data | `$XDG_DATA_HOME/sm0l/` or `~/.local/share/sm0l/` |
| Default workspace | `~/sm0l_workspace` (`OPERATIONS.md` is seeded there) |
| User install (default) | `~/.local/lib/sm0l`, `~/.local/bin/sm0l` |
| Desktop entry | `~/.local/share/applications/sm0l.desktop` |
| Icon | `~/.local/share/icons/hicolor/256x256/apps/sm0l.png` |
| Share assets | `~/.local/share/sm0l/assets/` |
| System install | `PREFIX=/usr/local sudo ./install.sh` |

`~` in a saved workspace path is expanded. File tools normalize CRLF to LF on write/edit so Windows-copied trees still patch cleanly.

## Run from source

```bash
chmod +x run.sh build.sh install.sh uninstall.sh
./run.sh
```

That creates `.venv` if needed and launches the dashboard. After a freeze, `./run.sh` prefers `dist/sm0l/sm0l`.

Manual:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python sm0l.py
```

1. Start Ollama (`ollama serve` if it is not already a service) **or** start LM Studio's local server (LM Studio → Developer tab → Start Server).
2. In the right panel, pick **Provider** (Ollama or LM Studio) and set **Host** if it's not the default.
   - Ollama: Pull `qwen2.5:7b` from the right panel (or Refresh if you already have a model).
   - LM Studio: download/load a model from LM Studio itself, then hit **Refresh** — sm0l has no pull API for LM Studio.
3. Set workspace if you want a project folder.
4. Type. Enter sends. Shift+Enter is a newline.
5. Paste, drop, or click **Image** to attach pictures to the message being composed (up to 4).

Attached images are stored in `$XDG_DATA_HOME/sm0l/media/` (or `~/.local/share/sm0l/media/`) and sent as vision attachments to whichever provider is selected. Use a vision-capable model (`qwen2.5vl`, `llava`, `minicpm-v`, …).

### LM Studio notes

- Default host: `http://127.0.0.1:1234`. sm0l talks to LM Studio's OpenAI-compatible `/api/v0/*` endpoints (model list, context length, chat + tool calling, streaming).
- Model pulling isn't exposed over LM Studio's API — get models via its Discover tab or the `lms` CLI, then **Refresh** in sm0l.
- Tool calling requires a model LM Studio has marked tool-capable; if a model rejects `tools`, sm0l retries once without them (same fallback as Ollama) and falls back to the `<tool_call>` XML convention.

## Build

```bash
./build.sh
```

That creates `.venv`, generates `assets/icon.png`, and writes `dist/sm0l/sm0l`.

## Install

User-local (default — no root):

```bash
./build.sh
./install.sh
sm0l
```

System-wide:

```bash
./build.sh
PREFIX=/usr/local sudo ./install.sh
```

`install.sh` copies the frozen tree when `dist/sm0l/sm0l` exists; otherwise it installs a source + venv wrapper. Uninstall does **not** delete config, sessions, or `~/sm0l_workspace`:

```bash
./uninstall.sh
# PREFIX=/usr/local sudo ./uninstall.sh
```

If `~/.local/bin` is not on your PATH, add it:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
```

## Design

| Constraint | How sm0l handles it |
|---|---|
| Small context | Detect native context window (Ollama `/api/show` or LM Studio `/api/v0/models`), compact at ~62% |
| Weak long-prompt following | RUNTIME + single OPERATIONS.md digest stay tiny |
| Tool-call drift | 8 tools, 8 round cap, XML fallback if native tools fail |
| Huge tool dumps | Hard clip on search/fetch/read/shell |
| No background noise | No heartbeat, no MEMORY.md spam |

## Tools

`search` `fetch` `read_file` `write_file` `edit_file` `list_dir` `grep` `shell`

Search uses the free DuckDuckGo instant-answer API plus HTML results. No API key.

`shell` runs under `/bin/bash` (falls back to `/bin/sh`) in a new session so Stop / timeout can kill the whole process group.

## License

MIT.
