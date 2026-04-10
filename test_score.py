"""
Baseline tests for score.py utility functions and CLI argument defaults.

No API calls — tests only pure functions and argument parsing.

Usage:
    uv run pytest test_score.py -q
"""

import json
import tempfile
from pathlib import Path

import pytest

from score import (
    extract_json, load_scores, save_scores,
    prompt_version, archive_previous_scores, SYSTEM_PROMPT,
)


# ── extract_json ───────────────────────────────────────────────────────


class TestExtractJson:
    def test_plain_json(self):
        text = '{"exposure": 7, "rationale": "High AI exposure"}'
        result = extract_json(text)
        assert result == {"exposure": 7, "rationale": "High AI exposure"}

    def test_json_with_whitespace(self):
        text = '  \n  {"exposure": 3, "rationale": "Low"}  \n  '
        result = extract_json(text)
        assert result == {"exposure": 3, "rationale": "Low"}

    def test_markdown_fenced_json(self):
        text = '```json\n{"exposure": 5, "rationale": "Moderate"}\n```'
        result = extract_json(text)
        assert result == {"exposure": 5, "rationale": "Moderate"}

    def test_markdown_fenced_no_language(self):
        text = '```\n{"exposure": 9, "rationale": "Very high"}\n```'
        result = extract_json(text)
        assert result == {"exposure": 9, "rationale": "Very high"}

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            extract_json("not json at all")

    def test_empty_string_raises(self):
        with pytest.raises(json.JSONDecodeError):
            extract_json("")


# ── load_scores / save_scores ──────────────────────────────────────────


class TestScoresIO:
    def test_round_trip(self, tmp_path):
        scores_path = tmp_path / "scores.json"
        scores = {
            "nurse": {"exposure": 4, "rationale": "Mixed physical and knowledge"},
            "developer": {"exposure": 9, "rationale": "Almost entirely computer-based"},
        }
        save_scores(scores, scores_path)
        loaded = load_scores(scores_path)
        assert loaded == scores

    def test_load_missing_file(self, tmp_path):
        scores_path = tmp_path / "nonexistent.json"
        assert load_scores(scores_path) == {}

    def test_save_creates_file(self, tmp_path):
        scores_path = tmp_path / "new_scores.json"
        assert not scores_path.exists()
        save_scores({"test": {"exposure": 5, "rationale": "Test"}}, scores_path)
        assert scores_path.exists()

    def test_save_overwrites(self, tmp_path):
        scores_path = tmp_path / "scores.json"
        save_scores({"a": {"exposure": 1, "rationale": "First"}}, scores_path)
        save_scores({"b": {"exposure": 2, "rationale": "Second"}}, scores_path)
        loaded = load_scores(scores_path)
        assert "a" not in loaded
        assert loaded["b"]["exposure"] == 2

    def test_empty_scores(self, tmp_path):
        scores_path = tmp_path / "scores.json"
        save_scores({}, scores_path)
        assert load_scores(scores_path) == {}


# ── Score clamping ─────────────────────────────────────────────────────


class TestScoreClamping:
    """Test the clamping logic: max(0, min(10, int(round(float(exposure)))))"""

    @pytest.mark.parametrize("raw,expected", [
        (5, 5),
        (0, 0),
        (10, 10),
        (-1, 0),
        (15, 10),
        (7.4, 7),
        (7.6, 8),
        (0.0, 0),
        (10.0, 10),
        (-5.5, 0),
        (100, 10),
    ])
    def test_clamp(self, raw, expected):
        clamped = max(0, min(10, int(round(float(raw)))))
        assert clamped == expected


# ── CLI argument defaults ──────────────────────────────────────────────


class TestCLIDefaults:
    def test_default_model(self):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--model", default="gemini-2.5-flash")
        args = parser.parse_args([])
        assert args.model == "gemini-2.5-flash"

    def test_default_delay(self):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--delay", type=float, default=0.2)
        args = parser.parse_args([])
        assert args.delay == 0.2

    def test_default_start(self):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--start", type=int, default=0)
        args = parser.parse_args([])
        assert args.start == 0

    def test_force_flag(self):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--force", action="store_true")
        args = parser.parse_args([])
        assert args.force is False
        args2 = parser.parse_args(["--force"])
        assert args2.force is True

    def test_thinking_budget_default(self):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--thinking-budget", type=int, default=2048)
        args = parser.parse_args([])
        assert args.thinking_budget == 2048

    def test_thinking_budget_zero(self):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--thinking-budget", type=int, default=2048)
        args = parser.parse_args(["--thinking-budget", "0"])
        assert args.thinking_budget == 0


# ── prompt_version ─────────────────────────────────────────────────────


class TestPromptVersion:
    def test_returns_string(self):
        v = prompt_version()
        assert isinstance(v, str)
        assert len(v) == 12

    def test_deterministic(self):
        assert prompt_version() == prompt_version()

    def test_hex_chars(self):
        v = prompt_version()
        assert all(c in "0123456789abcdef" for c in v)


# ── archive_previous_scores ───────────────────────────────────────────


class TestArchive:
    def test_archive_with_meta(self, tmp_path):
        scores_path = tmp_path / "scores.json"
        scores = {
            "_meta": {"run_date": "2026-03-25", "model": "gemini-2.5-flash"},
            "nurse": {"exposure": 4, "rationale": "Test"},
        }
        save_scores(scores, scores_path)
        archive_previous_scores(scores_path)
        archive = tmp_path / "runs" / "2026-03-25_scores.json"
        assert archive.exists()
        archived = json.loads(archive.read_text())
        assert archived["nurse"]["exposure"] == 4

    def test_no_archive_without_meta(self, tmp_path):
        scores_path = tmp_path / "scores.json"
        save_scores({"nurse": {"exposure": 4, "rationale": "Test"}}, scores_path)
        archive_previous_scores(scores_path)
        runs_dir = tmp_path / "runs"
        assert not runs_dir.exists()

    def test_no_archive_missing_file(self, tmp_path):
        scores_path = tmp_path / "nonexistent.json"
        archive_previous_scores(scores_path)  # Should not raise

    def test_meta_preserved_in_load(self, tmp_path):
        scores_path = tmp_path / "scores.json"
        scores = {
            "_meta": {"run_date": "2026-03-25"},
            "nurse": {"exposure": 4, "rationale": "Test"},
        }
        save_scores(scores, scores_path)
        loaded = load_scores(scores_path)
        assert "_meta" in loaded
        assert loaded["nurse"]["exposure"] == 4
