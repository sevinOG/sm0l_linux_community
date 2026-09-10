"""Headless checks — no GUI, no Ollama required."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.agent import parse_text_tool_calls
from src.compact import compact_threshold, estimate_tokens, split_for_compact
from src.lmstudio_client import _consume_sse
from src.media import attachments_to_b64, prepare_ollama_messages, prepare_openai_messages, save_encoded
from src.tools import clip, html_to_text, run_tool, tool_edit_file, tool_write_file


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"FAIL: {msg}")
    print("ok", msg)


def main() -> None:
    calls = parse_text_tool_calls(
        'hello <tool_call>{"name":"search","arguments":{"query":"qwen"}}</tool_call>'
    )
    check(len(calls) == 1 and calls[0]["function"]["name"] == "search", "xml tool parse")

    msgs = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "a" * 50},
        {"role": "assistant", "content": "b" * 50},
        {"role": "user", "content": "c" * 50},
        {"role": "assistant", "content": "d" * 50, "tool_calls": [{"function": {"name": "search"}}]},
        {"role": "tool", "content": "hits"},
        {"role": "user", "content": "now"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "again"},
    ]
    prefix, suffix = split_for_compact(msgs, keep_user_turns=2)
    check(suffix[0]["role"] == "user", "compact split on user turn")
    check(estimate_tokens(msgs) > 0, "token estimate")
    check(compact_threshold(32768) > 8000, "32k compact threshold")
    check(compact_threshold(8192) < compact_threshold(32768), "threshold scales with window")
    check("truncated" in clip("x" * 100, 20), "clip")
    check("Hello" in html_to_text("<html><script>x</script><p>Hello</p></html>"), "html text")

    tmp = ROOT / ".smoke_ws"
    tmp.mkdir(exist_ok=True)
    r = tool_write_file(tmp, "n.py", "print(1)\n")
    check("Wrote" in r, "write_file")
    r = tool_edit_file(tmp, "n.py", "print(1)", "print(2)")
    check("Edited" in r, "edit_file")
    r = run_tool("read_file", {"path": "n.py"}, tmp)
    check("print(2)" in r, "read_file")
    r = run_tool("list_dir", {"path": "."}, tmp)
    check("n.py" in r, "list_dir")

    r = run_tool("shell", {"command": "echo sm0l_ok && pwd"}, tmp)
    check("sm0l_ok" in r and "exit 0" in r, "shell")

    crlf = tmp / "crlf.txt"
    crlf.write_bytes(b"hello\r\nworld\r\n")
    r = tool_edit_file(tmp, "crlf.txt", "hello\nworld", "hello\nlinux")
    check("Edited" in r, "edit_file CRLF")
    body = (tmp / "crlf.txt").read_bytes()
    check(b"\r" not in body and b"hello\nlinux\n" == body, "edit_file writes LF")

    mixed = tmp / "win.py"
    mixed.write_bytes(b"print(1)\r\n")
    r = tool_write_file(tmp, "win.py", "print(3)\r\nprint(4)\r\n")
    check("Wrote" in r, "write_file CRLF input")
    check(b"\r" not in (tmp / "win.py").read_bytes(), "write_file stores LF")

    import os
    from src.paths import config_path, user_data, default_workspace

    os.environ["XDG_CONFIG_HOME"] = str(tmp / "xdg_config")
    os.environ["XDG_DATA_HOME"] = str(tmp / "xdg_data")
    check(str(config_path()).endswith("xdg_config/sm0l/config.json"), "config XDG path")
    check(str(user_data()).endswith("xdg_data/sm0l"), "data XDG path")
    check(default_workspace().name == "sm0l_workspace", "default workspace")

    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
    )
    att = save_encoded(png, "image/png", "dot.png")
    check(Path(att["path"]).is_file(), "media save")
    b64 = attachments_to_b64([att])
    check(len(b64) == 1 and len(b64[0]) > 8, "media b64")
    msgs = [{"role": "user", "content": "see", "attachments": [att]}]
    prep = prepare_ollama_messages(msgs)
    check("images" in prep[0] and "attachments" not in prep[0], "ollama images field")
    oa_prep = prepare_openai_messages(msgs)
    check(
        isinstance(oa_prep[0]["content"], list)
        and any(p.get("type") == "image_url" for p in oa_prep[0]["content"]),
        "openai image_url field",
    )
    tool_msgs = [
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "search", "arguments": {"query": "x"}}}]},
        {"role": "tool", "content": "hits", "tool_name": "search", "tool_call_id": "abc"},
    ]
    oa_tools = prepare_openai_messages(tool_msgs)
    check(
        isinstance(oa_tools[0]["tool_calls"][0]["function"]["arguments"], str),
        "openai tool_call arguments stringified",
    )
    check("tool_name" not in oa_tools[1] and oa_tools[1]["tool_call_id"] == "abc", "openai tool result shape")
    check(
        estimate_tokens(msgs) > estimate_tokens([{"role": "user", "content": "see"}]),
        "image token estimate",
    )

    # ---- LM Studio SSE reassembly: realistic fragmented tool-call deltas ----
    # Simulates: name/id on the first delta only, arguments split across many
    # chunks (including a split mid-string-escape), a chunk with empty
    # choices carrying partial usage, then a [DONE] marker followed by a
    # straggler usage-only chunk some servers send late. One garbage line is
    # mixed in to confirm a single bad chunk doesn't abort the stream.
    sse_lines = [
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","function":{"name":"search","arguments":""}}]}}]}',
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\"query\\""}}]}}]}',
        "data: not-json-garbage-should-be-skipped",
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":":\\"sm0l gith"}}]}}]}',
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"ub\\"}"}}]}}],"usage":{"prompt_tokens":42}}',
        'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}',
        "data: [DONE]",
        'data: {"usage":{"prompt_tokens":42,"completion_tokens":9}}',
    ]
    tokens: list[str] = []
    result = _consume_sse((ln.encode() for ln in sse_lines), on_token=tokens.append)
    calls = result["message"].get("tool_calls") or []
    check(len(calls) == 1, "sse: exactly one assembled tool call")
    check(calls[0]["id"] == "call_1", "sse: id from first delta survives later chunks")
    check(calls[0]["function"]["name"] == "search", "sse: name from first delta survives later chunks")
    check(
        json.loads(calls[0]["function"]["arguments"]) == {"query": "sm0l github"},
        "sse: fragmented arguments concatenated in order into valid JSON",
    )
    check(result["prompt_eval_count"] == 42, "sse: usage captured before [DONE]")
    check(result["eval_count"] == 9, "sse: usage arriving after [DONE] is not dropped")
    check(tokens == [], "sse: tool-call-only stream emits no content tokens")

    print("all smoke checks passed")


if __name__ == "__main__":
    main()
