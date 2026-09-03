"""Focused tests for P2 + P3 behavior changes. Runs offline, no Ollama."""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.compact import (
    compact_messages,
    compact_threshold,
    estimate_tokens,
    hard_trim_messages,
    calibrate_cpt,
    get_cpt,
    reset_calibration,
    message_chars,
    _prefix_text,
    _previous_memory,
    MAX_TRUNCATE_CHARS,
    MAX_LAST_USER_CHARS,
    MIN_SYSTEM_CHARS,
)


def _mk(role, content, **extra):
    m = {"role": role, "content": content}
    m.update(extra)
    return m


# ---- P2-1 calibration ----
def test_calibration_updates_cpt():
    reset_calibration()
    assert get_cpt() == 4.0
    # 4000 chars / 1000 tokens = cpt=4
    calibrate_cpt(4000, 1000)
    assert abs(get_cpt() - 4.0) < 0.5
    # 3000/500 = cpt=6 — should pull EMA toward 6
    for _ in range(5):
        calibrate_cpt(3000, 500)
    assert get_cpt() > 5.0
    # clamping: tiny ratio
    calibrate_cpt(100, 5000)  # 0.02 — clamp to _CPT_MIN=2
    assert get_cpt() >= 2.0
    # giant ratio
    calibrate_cpt(8000, 100)  # 80 — clamp to _CPT_MAX=8
    assert get_cpt() <= 8.0
    # bad inputs ignored
    before = get_cpt()
    calibrate_cpt(0, 100)
    calibrate_cpt(100, 0)
    assert get_cpt() == before
    print("  test_calibration_updates_cpt OK")


def test_estimate_uses_calibrated_cpt():
    reset_calibration()
    msgs = [_mk("user", "x" * 400)]
    base = estimate_tokens(msgs)
    # fake a high cpt (10 chars/token) -> fewer estimated tokens
    calibrate_cpt(10000, 1000)  # cpt=10 → clamped to 8
    high = estimate_tokens(msgs)
    assert high < base, f"high cpt should lower estimate (base={base}, high={high})"
    print("  test_estimate_uses_calibrated_cpt OK")


# ---- P2-2 compact blob budget ----
def test_prefix_text_respects_char_budget():
    # 1000 chars of content, budget 100 -> truncated
    msgs = [_mk("user", "y" * 1000) for _ in range(20)]
    out = _prefix_text(msgs, char_budget=100)
    assert len(out) <= 200, f"budget should bound output, got {len(out)}"
    # 50 chars of content, budget 1000 -> not truncated
    msgs2 = [_mk("user", "z" * 50) for _ in range(2)]
    out2 = _prefix_text(msgs2, char_budget=1000)
    assert out2.count("z") == 100  # all chars preserved
    print("  test_prefix_text_respects_char_budget OK")


def test_prefix_text_folds_prev_memory():
    msgs = [_mk("user", "new question")]
    prev = "Earlier we fixed the bug in src/agent.py"
    out = _prefix_text(msgs, char_budget=4000, prev_memory=prev)
    assert "Earlier summary" in out
    assert prev in out
    print("  test_prefix_text_folds_prev_memory OK")


# ---- P2-3 effective ctx shared ----
def test_compact_threshold_matches():
    # Threshold is computed from (ctx - OUTPUT_RESERVE) * ratio, floored at 1024
    expected_8k = max(int((8192 - 2048) * 0.62), 1024)
    assert compact_threshold(8192, 0.62) == expected_8k
    # Larger ctx -> larger threshold
    assert compact_threshold(16384, 0.62) > compact_threshold(8192, 0.62)
    # Floor: tiny ctx still returns >= 1024
    assert compact_threshold(512, 0.62) >= 1024
    print("  test_compact_threshold_matches OK")


# ---- P3-1 tool_call_id propagation ----
def test_tool_message_can_carry_id():
    # Simulate the shape Agent.run() appends
    msg = {
        "role": "tool",
        "content": "output",
        "name": "shell",
        "tool_name": "shell",
        "tool_call_id": "call_abc123",
    }
    assert msg.get("tool_call_id") == "call_abc123"
    # estimate_tokens shouldn't crash on tool_call_id
    n = estimate_tokens([msg])
    assert n > 0
    print("  test_tool_message_can_carry_id OK")


# ---- P3-2 previous memory lookup ----
def test_previous_memory_extracts_body():
    msgs = [
        _mk("system", "primary system prompt"),
        _mk("system", "[compacted memory — earlier turns]\nold summary body"),
        _mk("user", "hi"),
    ]
    assert _previous_memory(msgs) == "old summary body"
    assert _previous_memory([_mk("user", "hi")]) is None
    print("  test_previous_memory_extracts_body OK")


# ---- P3-3 softer hard-trim ----
def test_hard_trim_preserves_last_user_above_floor():
    # Build a list that is over thresh, where the last user turn is huge
    big = _mk("user", "U" * 8000)  # last user
    history = [_mk("assistant", "x" * 1000) for _ in range(8)]
    work = [_mk("system", "primary")] + history + [big]
    out = hard_trim_messages(work, thresh=500)
    last_user_idx = max(i for i, m in enumerate(out) if m.get("role") == "user")
    last = out[last_user_idx]
    # P3-3: last user content should be at least MAX_LAST_USER_CHARS (2000)
    assert len(last["content"]) >= MAX_LAST_USER_CHARS, (
        f"last user only {len(last['content'])} chars"
    )
    # and primary system should still exist
    assert any(
        m.get("role") == "system" and not str(m.get("content", "")).startswith("[compacted memory")
        for m in out
    )
    print("  test_hard_trim_preserves_last_user_above_floor OK")


def test_hard_trim_shrinks_memory_body_keeps_header():
    # Memory block + huge primary system + lots of history
    memory = _mk("system", "[compacted memory — earlier turns]\n" + ("M" * 6000))
    primary = _mk("system", "S" * 1000)  # system too
    history = [_mk("assistant", "a" * 500) for _ in range(6)]
    work = [primary, memory, *history, _mk("user", "hi")]
    out = hard_trim_messages(work, thresh=300)
    mem = next(
        m for m in out
        if m.get("role") == "system" and str(m.get("content", "")).startswith("[compacted memory")
    )
    body = mem["content"].split("\n", 1)[1]
    # P3-3: memory body should be at most MAX_TRUNCATE_CHARS
    assert len(body) <= MAX_TRUNCATE_CHARS + 1  # +1 for the trailing ellipsis char
    # and header preserved
    assert mem["content"].startswith("[compacted memory")
    print("  test_hard_trim_shrinks_memory_body_keeps_header OK")


def test_hard_trim_keeps_primary_system_above_floor():
    # Make a primary system huge so it has to be trimmed, but never below MIN_SYSTEM_CHARS
    primary = _mk("system", "S" * 5000)
    history = [_mk("assistant", "a" * 200) for _ in range(5)]
    work = [primary, *history, _mk("user", "hi")]
    out = hard_trim_messages(work, thresh=200)
    sys_kept = next(
        m for m in out
        if m.get("role") == "system" and not str(m.get("content", "")).startswith("[compacted memory")
    )
    assert len(sys_kept["content"]) >= MIN_SYSTEM_CHARS, (
        f"system trimmed below floor: {len(sys_kept['content'])}"
    )
    print("  test_hard_trim_keeps_primary_system_above_floor OK")


# ---- compact_messages error path doesn't crash on empty summary ----
def test_compact_messages_no_ollama(monkeypatch=None):
    # Don't call Ollama — just confirm compact_messages with no host returns
    # gracefully (no crash) by being under threshold.
    msgs = [_mk("system", "primary"), _mk("user", "hi")]
    out, note = compact_messages(
        host="http://127.0.0.1:1",  # unreachable
        model="fake",
        messages=msgs,
        num_ctx=8192,
    )
    assert isinstance(out, list)
    # under threshold -> no note
    assert note is None
    print("  test_compact_messages_no_ollama OK")


def main():
    print("P2 + P3 behavior tests")
    test_calibration_updates_cpt()
    test_estimate_uses_calibrated_cpt()
    test_prefix_text_respects_char_budget()
    test_prefix_text_folds_prev_memory()
    test_compact_threshold_matches()
    test_tool_message_can_carry_id()
    test_previous_memory_extracts_body()
    test_hard_trim_preserves_last_user_above_floor()
    test_hard_trim_shrinks_memory_body_keeps_header()
    test_hard_trim_keeps_primary_system_above_floor()
    test_compact_messages_no_ollama()
    print("ALL OK")


if __name__ == "__main__":
    main()
