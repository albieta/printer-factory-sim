"""Tests for engine.agent_runner.

Coverage:
1. Subprocess command args — verifies --verbose and --output-format stream-json are present.
2. _parse_stream_json — verifies correct extraction from synthetic stream-json payloads.
3. Integration smoke test — calls real claude CLI with a trivial prompt (skipped if
   SKIP_CLAUDE_INTEGRATION env var is set, or if claude is not on PATH).
"""

from __future__ import annotations

import inspect
import json
import subprocess
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from engine.agent_runner import DEFAULT_TIMEOUT, _parse_stream_json, run_agent


# ── 1. Subprocess command-line flags ─────────────────────────────────────────


def _captured_cmd(run_agent_result: Any) -> list[str]:
    """Return the command list from a mock subprocess.run call."""
    return run_agent_result


def test_claude_subprocess_includes_verbose(tmp_path: Path) -> None:
    """run_agent must pass --verbose so stream-json output format works."""
    skill_file = tmp_path / "skill.md"
    skill_file.write_text("# Test skill\nDo nothing.")
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()

    captured_cmd: list[str] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> Any:
        captured_cmd.extend(cmd)
        mock = MagicMock()
        mock.stdout = ""
        mock.stderr = ""
        mock.returncode = 0
        return mock

    with patch("engine.agent_runner.subprocess.run", side_effect=fake_run):
        with patch("engine.agent_runner.LOGS_DIR", logs_dir):
            run_agent(
                role="TestRole",
                day=1,
                prompt="Say done.",
                skill_file=str(skill_file),
                cwd=str(tmp_path),
            )

    assert "claude" in captured_cmd[0], "first arg must be 'claude'"
    assert "--verbose" in captured_cmd, "--verbose flag must be present for stream-json mode"
    assert "--output-format" in captured_cmd, "--output-format flag must be present"
    idx = captured_cmd.index("--output-format")
    assert captured_cmd[idx + 1] == "stream-json", "output format must be stream-json"
    assert "--print" in captured_cmd, "--print flag must be present"


def test_claude_subprocess_timeout_is_adequate() -> None:
    """DEFAULT_TIMEOUT must be at least 120s to handle real LLM agents."""
    assert DEFAULT_TIMEOUT >= 120, (
        f"DEFAULT_TIMEOUT={DEFAULT_TIMEOUT} is too low; LLM agents need at least 120s"
    )


# ── 2. _parse_stream_json unit tests ─────────────────────────────────────────


def _make_stream_json_lines(*payloads: dict[str, Any]) -> str:
    return "\n".join(json.dumps(p) for p in payloads)


def test_parse_stream_json_empty() -> None:
    tool_calls, text = _parse_stream_json("")
    assert tool_calls == []
    assert text == ""


def test_parse_stream_json_final_text_only() -> None:
    """A stream with only a text response, no tool calls."""
    lines = _make_stream_json_lines(
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": "Hello from Claude"}]
            },
        }
    )
    tool_calls, text = _parse_stream_json(lines)
    assert tool_calls == []
    assert "Hello from Claude" in text


def test_parse_stream_json_single_bash_call() -> None:
    """A stream with one Bash tool call followed by its result."""
    lines = _make_stream_json_lines(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_abc123",
                        "name": "Bash",
                        "input": {"command": "bin/manufacturer-cli capacity"},
                    }
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_abc123",
                        "content": "Lines: 1\nWorkers: 1",
                    }
                ]
            },
        },
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": "- Day 1 complete.\n- Released 3 orders."}]
            },
        },
    )
    tool_calls, text = _parse_stream_json(lines)
    assert len(tool_calls) == 1
    assert tool_calls[0]["tool"] == "Bash"
    assert tool_calls[0]["command"] == "bin/manufacturer-cli capacity"
    assert "Lines: 1" in tool_calls[0]["stdout"]
    assert "Day 1 complete" in text


def test_parse_stream_json_multiple_bash_calls() -> None:
    """Parser correctly tracks multiple sequential tool calls by ID."""
    lines = _make_stream_json_lines(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "cmd1"}},
                    {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "cmd2"}},
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "out1"}]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [{"type": "tool_result", "tool_use_id": "t2", "content": "out2"}]
            },
        },
        {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Done."}]},
        },
    )
    tool_calls, text = _parse_stream_json(lines)
    assert len(tool_calls) == 2
    assert tool_calls[0]["command"] == "cmd1"
    assert tool_calls[0]["stdout"] == "out1"
    assert tool_calls[1]["command"] == "cmd2"
    assert tool_calls[1]["stdout"] == "out2"
    assert text == "Done."


def test_parse_stream_json_ignores_garbage_lines() -> None:
    """Non-JSON lines (e.g. progress dots) must not crash the parser."""
    mixed = "not json at all\n" + json.dumps(
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "OK"}]}}
    )
    tool_calls, text = _parse_stream_json(mixed)
    assert tool_calls == []
    assert "OK" in text


# ── 3. Integration smoke test ─────────────────────────────────────────────────


def _claude_on_path() -> bool:
    try:
        subprocess.run(["claude", "--version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@pytest.mark.skipif(not _claude_on_path(), reason="claude CLI not on PATH")
def test_claude_subprocess_stream_json_verbose_flag_works(tmp_path: Path) -> None:
    """Real subprocess call — verifies --verbose + --output-format stream-json combination
    works end-to-end (no 'requires --verbose' error)."""
    result = subprocess.run(
        [
            "claude",
            "--print",
            "--verbose",
            "--output-format",
            "stream-json",
            "--permission-mode",
            "bypassPermissions",
            "--allowedTools",
            "Bash",
            "--",
            "Print only the word DONE. Do not use any tools.",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(tmp_path),
    )
    assert "requires --verbose" not in result.stderr, (
        f"claude rejected the flags: {result.stderr[:300]}"
    )
    assert result.returncode == 0, (
        f"claude exited {result.returncode}; stderr: {result.stderr[:300]}"
    )
    # The output should be parseable stream-json with at least one assistant message
    parsed_lines = [json.loads(l) for l in result.stdout.splitlines() if l.strip()]
    assert any(l.get("type") == "assistant" for l in parsed_lines), (
        "Expected at least one 'assistant' event in stream-json output"
    )
    _, text = _parse_stream_json(result.stdout)
    assert text.strip(), "Expected non-empty final text from claude"


@pytest.mark.skipif(not _claude_on_path(), reason="claude CLI not on PATH")
def test_run_agent_returns_nonempty_output(tmp_path: Path) -> None:
    """Full run_agent() call — verifies final text is non-empty for a trivial prompt."""
    skill_file = tmp_path / "skill.md"
    skill_file.write_text(
        textwrap.dedent("""\
            # Test Skill
            When done, print exactly: - Test complete.
        """)
    )
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()

    with patch("engine.agent_runner.LOGS_DIR", logs_dir):
        output = run_agent(
            role="TestRole",
            day=1,
            prompt="Print only: - Test complete. Do not use tools.",
            skill_file=str(skill_file),
            cwd=str(tmp_path),
            timeout_seconds=60,
        )

    assert output.strip(), "run_agent must return non-empty output"
    log_file = logs_dir / "day-001-TestRole.log"
    assert log_file.exists(), "log file must be written"
    log_text = log_file.read_text()
    assert "PROMPT SENT TO CLAUDE" in log_text
    assert "CLAUDE FINAL RESPONSE" in log_text
