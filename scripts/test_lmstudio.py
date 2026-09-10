"""Optional live integration check against a running LM Studio server.

Unlike smoke.py / _test_p2p3.py this talks to a real server, so it's not
part of the no-network test path — it SKIPS (exit 0) unless LMSTUDIO_HOST
is set:

    # Start LM Studio -> Developer tab -> Start Server, load a model, then:
    LMSTUDIO_HOST=http://127.0.0.1:1234 .venv/bin/python scripts/test_lmstudio.py

    # Pin a specific loaded model instead of using the first one listed:
    LMSTUDIO_MODEL=qwen2.5-7b-instruct LMSTUDIO_HOST=http://127.0.0.1:1234 \
        .venv/bin/python scripts/test_lmstudio.py

Exercises the same client surface agent.py drives: ping, list_models,
native_context_length, a plain chat_once round trip, a streamed chat_stream
round trip, and one streamed tool-calling round trip (tolerant of models
that answer without calling a tool — not every local model is tool-tuned).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import lmstudio_client as lms
from src.tools import SCHEMAS


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"FAIL: {msg}")
    print("ok", msg)


def main() -> None:
    host = (os.environ.get("LMSTUDIO_HOST") or "").strip()
    if not host:
        print(
            "SKIP: set LMSTUDIO_HOST (e.g. http://127.0.0.1:1234) to run this "
            "against a live LM Studio server. Start LM Studio's Developer tab "
            "server and load a model first."
        )
        return

    check(lms.ping(host), f"LM Studio reachable at {host}")

    models = lms.list_models(host)
    check(len(models) > 0, "at least one chat-capable model listed")
    model = (os.environ.get("LMSTUDIO_MODEL") or "").strip() or models[0]["name"]
    print(f"using model: {model}")

    ctx = lms.native_context_length(host, model)
    check(ctx > 0, f"native context length reported ({ctx})")

    once = lms.chat_once(
        host,
        model,
        [
            {"role": "system", "content": "Reply with exactly one word: pong"},
            {"role": "user", "content": "ping"},
        ],
        options={"temperature": 0.0, "num_predict": 16},
        timeout=60,
    )
    once_content = (once.get("message") or {}).get("content") or ""
    check(bool(once_content.strip()), f"chat_once returned content: {once_content!r}")

    tokens: list[str] = []
    streamed = lms.chat_stream(
        host,
        model,
        [{"role": "user", "content": "Count from 1 to 3, one number per line."}],
        options={"temperature": 0.0, "num_predict": 32},
        on_token=tokens.append,
        timeout=60,
    )
    check(len(tokens) > 0, "chat_stream emitted at least one token via on_token")
    check(bool((streamed.get("message") or {}).get("content")), "chat_stream assembled non-empty content")

    tool_turn = lms.chat_stream(
        host,
        model,
        [{"role": "user", "content": "Use the search tool to look up 'sm0l github'."}],
        tools=SCHEMAS,
        options={"temperature": 0.0, "num_predict": 128},
        timeout=60,
    )
    tool_calls = (tool_turn.get("message") or {}).get("tool_calls") or []
    if tool_calls:
        names = [ (tc.get("function") or {}).get("name") for tc in tool_calls ]
        check(all(names), f"tool call(s) carry a function name: {names}")
        print(f"ok model called tool(s): {names}")
    else:
        print("note: model answered without calling a tool (fine for a non-tool-tuned model)")

    try:
        lms.pull_model(host, "anything")
        raise SystemExit("FAIL: pull_model should always raise for LM Studio")
    except RuntimeError:
        print("ok pull_model raises RuntimeError (no pull API — expected)")

    print("all LM Studio live integration checks passed")


if __name__ == "__main__":
    main()
