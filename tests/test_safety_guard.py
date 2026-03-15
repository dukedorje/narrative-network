"""Unit tests for orchestrator.safety_guard.PathSafetyGuard."""

from __future__ import annotations

import pytest

from subnet.config import MAX_HOP_WORDS, MIN_HOP_WORDS
from orchestrator.safety_guard import PathSafetyGuard


# ---------------------------------------------------------------------------
# filter_candidates
# ---------------------------------------------------------------------------


def test_filter_removes_visited():
    guard = PathSafetyGuard()
    result = guard.filter_candidates(["a", "b", "c"], visited_path=["a", "c"])
    assert result == ["b"]


def test_filter_keeps_unvisited():
    guard = PathSafetyGuard()
    result = guard.filter_candidates(["x", "y", "z"], visited_path=["a"])
    assert result == ["x", "y", "z"]


def test_filter_empty_path():
    guard = PathSafetyGuard()
    candidates = ["n1", "n2", "n3"]
    result = guard.filter_candidates(candidates, visited_path=[])
    assert result == candidates


def test_filter_all_visited():
    guard = PathSafetyGuard()
    result = guard.filter_candidates(["a", "b"], visited_path=["a", "b", "c"])
    assert result == []


def test_filter_preserves_order():
    guard = PathSafetyGuard()
    candidates = ["z", "m", "a", "b"]
    result = guard.filter_candidates(candidates, visited_path=["m"])
    assert result == ["z", "a", "b"]


# ---------------------------------------------------------------------------
# check_passage
# ---------------------------------------------------------------------------


def test_check_passage_valid():
    guard = PathSafetyGuard()
    # Build a passage with exactly MIN_HOP_WORDS + 50 words (safely in range)
    passage = " ".join(["word"] * (MIN_HOP_WORDS + 50))
    ok, reason = guard.check_passage(passage)
    assert ok is True
    assert reason == ""


def test_check_passage_too_short():
    guard = PathSafetyGuard()
    passage = " ".join(["word"] * 10)
    ok, reason = guard.check_passage(passage)
    assert ok is False
    assert "short" in reason.lower()


def test_check_passage_too_long():
    guard = PathSafetyGuard()
    passage = " ".join(["word"] * (MAX_HOP_WORDS + 50))
    ok, reason = guard.check_passage(passage)
    assert ok is False
    assert "long" in reason.lower()


def test_check_passage_exactly_min_words():
    guard = PathSafetyGuard()
    passage = " ".join(["word"] * MIN_HOP_WORDS)
    ok, reason = guard.check_passage(passage)
    assert ok is True


def test_check_passage_exactly_max_words():
    guard = PathSafetyGuard()
    passage = " ".join(["word"] * MAX_HOP_WORDS)
    ok, reason = guard.check_passage(passage)
    assert ok is True


def test_check_passage_one_over_max():
    guard = PathSafetyGuard()
    passage = " ".join(["word"] * (MAX_HOP_WORDS + 1))
    ok, reason = guard.check_passage(passage)
    assert ok is False


def test_check_passage_one_under_min():
    guard = PathSafetyGuard()
    passage = " ".join(["word"] * (MIN_HOP_WORDS - 1))
    ok, reason = guard.check_passage(passage)
    assert ok is False


# ---------------------------------------------------------------------------
# check_path_length
# ---------------------------------------------------------------------------


def test_check_path_length_ok():
    guard = PathSafetyGuard(max_hops=5)
    ok, reason = guard.check_path_length(["a", "b", "c"])
    assert ok is True
    assert reason == ""


def test_check_path_length_exceeded():
    guard = PathSafetyGuard(max_hops=3)
    ok, reason = guard.check_path_length(["a", "b", "c"])
    assert ok is False
    assert "3" in reason


def test_check_path_length_empty():
    guard = PathSafetyGuard(max_hops=20)
    ok, reason = guard.check_path_length([])
    assert ok is True


def test_check_path_length_one_under_max():
    guard = PathSafetyGuard(max_hops=5)
    ok, reason = guard.check_path_length(["a", "b", "c", "d"])  # 4 hops
    assert ok is True


# ---------------------------------------------------------------------------
# tick
# ---------------------------------------------------------------------------


def test_tick_increments():
    guard = PathSafetyGuard()
    assert guard._tick_count == 0
    guard.tick()
    assert guard._tick_count == 1
    guard.tick()
    guard.tick()
    assert guard._tick_count == 3
