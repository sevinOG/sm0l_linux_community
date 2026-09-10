# LM Studio provider — manual verification

`scripts/smoke.py` and `scripts/_test_p2p3.py` cover the message-shaping and
SSE-reassembly logic without a network. `scripts/test_lmstudio.py` covers a
live round trip against a real server (see its docstring). Neither can
exercise the actual dashboard against real LM Studio models — use this
checklist for that, e.g. before a release or after touching
`src/lmstudio_client.py`, `src/providers.py`, or the provider bits of
`src/ui.py` / `src/agent.py`.

## Setup

1. Install and open [LM Studio](https://lmstudio.ai).
2. **Developer** tab → **Start Server** (default `http://127.0.0.1:1234`).
3. Download at least:
   - a normal chat model (e.g. `qwen2.5-7b-instruct`)
   - a vision-capable model (e.g. `qwen2.5-vl-7b-instruct`)
   - a model known to support tool calling (check LM Studio's model card —
     not every local model does)
4. Load at least one model in LM Studio so `/api/v0/models` reports it.

## Checklist

- [ ] **Switch provider** — in sm0l's Settings panel, set Provider to
      "LM Studio". Host field should switch to `http://127.0.0.1:1234`
      (or whatever was last saved for LM Studio).
- [ ] **Refresh models** — click Refresh; the model dropdown lists the
      LM Studio models from step 3/4, not stale Ollama names.
- [ ] **Plain chat** — send a normal message to the chat model, get a
      reasonable reply.
- [ ] **Streaming** — confirm tokens appear incrementally in the UI rather
      than all at once at the end.
- [ ] **Tool calling** — ask something that requires `search`, `read_file`,
      or `shell` (e.g. "search the web for X" / "list files in this repo" /
      "run `echo hi`") against the tool-capable model. Confirm the tool
      actually runs (visible in the TOOLS panel) and the result comes back
      into the conversation.
- [ ] **Tools-unsupported fallback** — repeat the tool-calling test against
      a model that does *not* support tool calling. sm0l should retry the
      turn without `tools` (see `chat_stream`'s retry-without-tools branch
      in both `lmstudio_client.py` and `ollama_client.py`) instead of
      failing the turn outright. It's fine if the model just answers in
      prose without calling anything — the point is no crash / no stuck
      turn.
- [ ] **Image attachment** — switch to the vision model, attach an image
      (paste, drag-drop, or the Image button), ask about it, confirm the
      model actually describes the image content (not a generic "I can't
      see images" refusal, which would mean the `image_url` payload isn't
      reaching the model).
- [ ] **Context compaction** — have a long enough conversation (or lower
      `num_ctx` in Settings to force it sooner) to trigger a compact; watch
      the TOOLS/status area for a compact note, confirm the conversation
      keeps working afterward.
- [ ] **Cancel mid-stream** — send a message that will produce a long
      response, hit Stop partway through, confirm the UI returns to ready
      state without hanging or throwing.
- [ ] **Pull button disabled** — with Provider = LM Studio, confirm the
      Pull button is disabled and its field explains models come from LM
      Studio's Discover tab / `lms get`, not from sm0l.
- [ ] **Switch back to Ollama** — confirm the Host field and model list
      swap back to the Ollama-side values without needing to retype
      anything (each provider remembers its own host).

## Known limitations

- LM Studio has no REST endpoint for pulling/downloading models, so sm0l's
  Pull button is Ollama-only by design (see checklist item above).
- `native_context_length` reads `loaded_context_length` /
  `max_context_length` from `/api/v0/models`. Some older LM Studio builds
  may not report these fields for every model type; sm0l falls back to
  8192 in that case, same as an unreadable Ollama `/api/show` response.
- Tool-calling quality depends entirely on the loaded model/quantization —
  sm0l does not do anything LM-Studio-specific to improve it beyond the
  existing retry-without-tools and `<tool_call>` XML fallback that already
  exist for Ollama.
