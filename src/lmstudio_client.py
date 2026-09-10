"""Thin LM Studio HTTP client. stdlib only — keeps the freeze small.

LM Studio speaks an OpenAI-compatible API. We use its `/api/v0/*` routes
(rather than plain `/v1/*`) because they report extra fields — notably
`max_context_length` / `loaded_context_length` — that Ollama exposes via
`/api/show`. Same public surface as `ollama_client.py` so `agent.py` /
`compact.py` / `ui.py` can call either client through `providers.py`.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
import uuid
from typing import Any, Callable, Iterable
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


def _url(host: str, path: str) -> str:
    base = host.rstrip("/") + "/"
    return urljoin(base, path.lstrip("/"))


def _request(
    host: str,
    path: str,
    payload: dict | None = None,
    method: str | None = None,
    timeout: float = 30,
) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        _url(host, path),
        data=data,
        headers=headers,
        method=method or ("POST" if data else "GET"),
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LM Studio HTTP {e.code}: {body[:400]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"LM Studio unreachable at {host}: {e.reason}") from e


def ping(host: str) -> bool:
    try:
        _request(host, "/api/v0/models", timeout=3)
        return True
    except Exception:
        return False


def list_models(host: str) -> list[dict]:
    data = _request(host, "/api/v0/models", timeout=8)
    entries = data.get("data") or []
    out = []
    for m in entries:
        name = m.get("id") or ""
        if not name:
            continue
        mtype = m.get("type") or "llm"
        if mtype not in ("llm", "vlm"):
            continue  # skip embedding models — not chat-capable
        out.append(
            {
                "name": name,
                "size": 0,
                "param": "",
                "family": m.get("arch") or "",
            }
        )
    out.sort(key=lambda x: x["name"].lower())
    return out


def native_context_length(host: str, name: str) -> int:
    """Read the model's window from /api/v0/models. Fall back to 8192."""
    try:
        data = _request(host, "/api/v0/models", timeout=8)
    except Exception:
        return 8192
    for m in data.get("data") or []:
        if m.get("id") != name:
            continue
        ctx = m.get("loaded_context_length") or m.get("max_context_length") or 0
        try:
            ctx = int(ctx)
        except (TypeError, ValueError):
            ctx = 0
        return ctx if ctx > 0 else 8192
    return 8192


def effective_num_ctx(host: str, model: str, override: int) -> int:
    native = native_context_length(host, model)
    if override and override > 0:
        return min(override, native if native else override)
    return native


def _stringify_args(args: Any) -> str:
    if isinstance(args, str):
        return args
    try:
        return json.dumps(args or {}, ensure_ascii=False)
    except Exception:
        return "{}"


def _assemble_message(content: str, tool_calls: dict[int, dict]) -> dict:
    """Finalize accumulated streaming/non-streaming tool-call slots into a
    message. Logs (never raises) when a call looks broken, so a bad delta
    sequence from a given model/server is easy to spot in the logs instead
    of silently producing a tool call the agent loop can't use.
    """
    message: dict[str, Any] = {"role": "assistant", "content": content}
    ordered = [tool_calls[i] for i in sorted(tool_calls)]
    for tc in ordered:
        if not tc.get("id"):
            tc["id"] = uuid.uuid4().hex
        fn = tc.get("function") or {}
        name = fn.get("name") or ""
        args = fn.get("arguments") or ""
        if not name:
            logger.warning("LM Studio tool call arrived with no function name: %r", tc)
        if args:
            try:
                json.loads(args)
            except json.JSONDecodeError:
                logger.warning(
                    "LM Studio tool call %r has malformed JSON arguments (likely a dropped "
                    "or out-of-order SSE chunk): %r",
                    name or "?",
                    args[:300],
                )
    if ordered:
        message["tool_calls"] = ordered
    return message


def _consume_sse(
    lines: Iterable[bytes | str],
    *,
    on_token: Callable[[str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict:
    """Parse an OpenAI-style `text/event-stream` body into assembled content,
    tool calls, and usage. Split out from `chat_stream` so this reassembly
    logic is unit-testable with a plain list of lines — no live server or
    urllib mocking needed.

    Defensive by design because real servers are messier than the spec:
    - Tool-call `arguments` routinely arrive as many small string fragments
      across separate deltas; they are concatenated in event order.
    - `id` / `function.name` are often sent once on the first delta for a
      given `index` and omitted afterward — later deltas only patch
      `arguments`, so a slot's `id`/`name` are only overwritten when a chunk
      actually carries a truthy value.
    - `usage` (and, on some servers, a final near-empty chunk) can show up
      attached to a chunk whose `choices` is empty, or even after the
      `[DONE]` marker — `[DONE]` is treated as "stop expecting content", not
      "stop reading the stream".
    - A single malformed chunk (bad JSON, unexpected shape) is logged and
      skipped rather than aborting the whole turn.
    """
    content = ""
    tool_calls: dict[int, dict] = {}
    prompt_eval = 0
    eval_count = 0
    done = False

    for raw in lines:
        if should_cancel and should_cancel():
            break
        line = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
        line = line.strip()
        if not line or not line.startswith("data:"):
            continue
        line = line[len("data:"):].strip()
        if line == "[DONE]":
            # Keep reading — some servers trail a usage-only chunk after this.
            done = True
            continue
        try:
            chunk = json.loads(line)
        except json.JSONDecodeError:
            logger.debug("LM Studio stream: skipping non-JSON chunk: %r", line[:200])
            continue
        if not isinstance(chunk, dict):
            continue
        try:
            if not done:
                choices = chunk.get("choices") or []
                if choices and isinstance(choices[0], dict):
                    delta = choices[0].get("delta") or {}
                    piece = delta.get("content") or ""
                    if piece:
                        content += piece
                        if on_token:
                            on_token(piece)
                    for tc in delta.get("tool_calls") or []:
                        if not isinstance(tc, dict):
                            continue
                        idx = tc.get("index", 0)
                        slot = tool_calls.setdefault(
                            idx,
                            {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
                        )
                        if tc.get("id"):
                            slot["id"] = tc["id"]
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            slot["function"]["name"] = fn["name"]
                        if fn.get("arguments"):
                            slot["function"]["arguments"] += fn["arguments"]
            usage = chunk.get("usage") or {}
            if usage.get("prompt_tokens"):
                prompt_eval = int(usage["prompt_tokens"])
            if usage.get("completion_tokens"):
                eval_count = int(usage["completion_tokens"])
        except Exception:
            logger.debug("LM Studio stream: malformed chunk, skipping: %r", chunk, exc_info=True)
            continue

    return {
        "message": _assemble_message(content, tool_calls),
        "prompt_eval_count": prompt_eval,
        "eval_count": eval_count,
    }


def chat_once(
    host: str,
    model: str,
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
    options: dict | None = None,
    think: bool | None = None,
    timeout: float = 180,
) -> dict:
    from .media import prepare_openai_messages

    options = options or {}
    payload: dict[str, Any] = {
        "model": model,
        "messages": prepare_openai_messages(messages),
        "stream": False,
    }
    if "temperature" in options:
        payload["temperature"] = options["temperature"]
    if options.get("num_predict"):
        payload["max_tokens"] = options["num_predict"]
    if tools:
        payload["tools"] = tools
    data = _request(host, "/api/v0/chat/completions", payload, timeout=timeout)
    choices = data.get("choices") or []
    msg = (choices[0].get("message") if choices else {}) or {}
    usage = data.get("usage") or {}
    tool_calls: dict[int, dict] = {}
    for i, tc in enumerate(msg.get("tool_calls") or []):
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") or {}
        tool_calls[i] = {
            "id": tc.get("id") or "",
            "type": "function",
            "function": {"name": fn.get("name") or "", "arguments": _stringify_args(fn.get("arguments"))},
        }
    return {
        "message": _assemble_message(msg.get("content") or "", tool_calls),
        "prompt_eval_count": int(usage.get("prompt_tokens") or 0),
        "eval_count": int(usage.get("completion_tokens") or 0),
    }


def chat_stream(
    host: str,
    model: str,
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
    options: dict | None = None,
    think: bool | None = None,
    timeout: float = 600,
    on_token: Callable[[str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict:
    """
    Stream a chat turn over LM Studio's OpenAI-compatible SSE endpoint.
    Returns the assembled assistant message plus usage, same shape as
    ollama_client.chat_stream: {message, prompt_eval_count, eval_count, used_tools_api}
    """
    from .media import prepare_openai_messages

    options = options or {}
    base_payload: dict[str, Any] = {
        "model": model,
        "messages": prepare_openai_messages(messages),
        "stream": True,
    }
    if "temperature" in options:
        base_payload["temperature"] = options["temperature"]
    if options.get("num_predict"):
        base_payload["max_tokens"] = options["num_predict"]

    def _run(with_tools: bool) -> dict:
        body = dict(base_payload)
        if with_tools and tools:
            body["tools"] = tools
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            _url(host, "/api/v0/chat/completions"),
            data=data,
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = _consume_sse(resp, on_token=on_token, should_cancel=should_cancel)
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LM Studio HTTP {e.code}: {err[:400]}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"LM Studio unreachable at {host}: {e.reason}") from e
        result["used_tools_api"] = with_tools
        return result

    try:
        return _run(bool(tools))
    except RuntimeError as e:
        text = str(e).lower()
        if tools and ("tool" in text or "does not support" in text or "400" in text):
            return _run(False)
        raise


def pull_model(
    host: str,
    name: str,
    on_status: Callable[[str], None] | None = None,
    timeout: float = 3600,
) -> None:
    raise RuntimeError(
        "LM Studio has no API to pull models. Download it from LM Studio's "
        f"Discover tab (or `lms get {name}` on the CLI), then hit Refresh."
    )
