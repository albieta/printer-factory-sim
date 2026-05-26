"""Subprocess wrapper for ``claude --print`` agent invocations.

Phase 1 (deterministic): ``run_agent`` is given ``skill_file=None`` and
returns immediately with a stub log line.

Phase 2 (one agent): a non-None ``skill_file`` triggers a real
``claude --print`` subprocess with stream-json output.  The result is written to
``logs/day-{day:03d}-{role}.log`` with complete flow:
  - Full prompt sent to Claude
  - Complete Claude output (text responses)
  - All tool invocations with results

Bash invocations are also logged separately to
``logs/day-{day:03d}-bash-calls.jsonl`` for visibility.

Timeout behaviour: if ``claude --print`` exceeds ``timeout_seconds``, the
runner logs a ``[timeout]`` marker and returns the partial output.  A stuck
agent never freezes the simulation.

Fast mode: when ``fast_mode=True``, the appropriate scripted agent from
``engine.scripted_agents`` is called instead of spawning a claude subprocess.
This is deterministic, free, and ~60× faster per day.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Optional

from engine.bash_logger import BashLogger


LOGS_DIR = Path("logs")
DEFAULT_TIMEOUT = 90  # reduced from 180 — with state pre-fetched agents need fewer tool calls


def _log_path(day: int, role: str) -> Path:
    return LOGS_DIR / f"day-{day:03d}-{role}.log"


def run_agent(
    role: str,
    day: int,
    prompt: str,
    skill_file: Optional[str],
    cwd: str = ".",
    timeout_seconds: int = DEFAULT_TIMEOUT,
    model: str = "claude-haiku-4-5-20251001",
    fast_mode: bool = False,
    role_cfg: Optional[dict[str, Any]] = None,
    signal: Optional[dict[str, Any]] = None,
) -> str:
    """Run the agent for *role* on *day* and return its output.

    If *skill_file* is ``None``, the stub path is taken.

    If *fast_mode* is ``True`` and *role_cfg* is provided, the scripted agent
    from ``engine.scripted_agents`` runs instead of a claude subprocess.

    Log format: for skill_file agents, logs complete flow:
    1. Full prompt sent to Claude
    2. Claude's tool invocations with results (from stream-json output)
    3. Claude's final response text
    4. Bash commands also logged to separate JSONL file
    """

    LOGS_DIR.mkdir(exist_ok=True)
    log = _log_path(day, role)

    # ── Fast mode: scripted deterministic agent ───────────────────────────────
    if fast_mode and role_cfg is not None:
        from engine.scripted_agents import (
            run_scripted_manufacturer,
            run_scripted_provider,
            run_scripted_retailer,
        )
        _signal = signal or {}
        role_lower = role.lower()
        if "provider" in role_lower or "supply" in role_lower or "chip" in role_lower:
            return run_scripted_provider(role, day, _signal, role_cfg)
        elif "retail" in role_lower or "printer" in role_lower or "world" in role_lower:
            return run_scripted_retailer(role, day, _signal, role_cfg)
        else:
            return run_scripted_manufacturer(role, day, _signal, role_cfg)

    bash_logger = BashLogger(day, role=role) if skill_file is not None else None

    if skill_file is None:
        output = f"[stub] {role} would decide here (day {day})\n"
        log.write_text(output, encoding="utf-8")
        return output

    try:
        result = subprocess.run(
            [
                "claude",
                "--print",
                "--output-format",
                "stream-json",
                "--permission-mode",
                "bypassPermissions",
                "--allowedTools",
                "Bash",
                "--model",
                model,
                "--add-dir",
                str(Path(cwd).resolve()),
                "--",
                prompt,
            ],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout_seconds,
        )
        raw_output = result.stdout
        stderr = result.stderr or ""
        exit_code = result.returncode
    except subprocess.TimeoutExpired as exc:
        partial = (exc.stdout or b"").decode("utf-8", errors="replace")
        raw_output = partial + f"\n[timeout] {role} agent exceeded {timeout_seconds}s on day {day}\n"
        stderr = ""
        exit_code = 124

    # Parse stream-json output to extract tool calls and final response
    tool_invocations, final_text = _parse_stream_json(raw_output)

    # Extract and log bash commands if logger exists
    if bash_logger:
        for invocation in tool_invocations:
            if invocation["tool"] == "Bash":
                bash_logger.log(
                    command=invocation["command"],
                    stdout=invocation.get("stdout", ""),
                    stderr=invocation.get("stderr", ""),
                    exit_code=invocation.get("exit_code", 0),
                )

    # Build complete log showing flow: prompt → tool calls → response
    log_content = (
        "=== PROMPT SENT TO CLAUDE ===\n"
        f"{prompt}\n\n"
        "=== TOOL INVOCATIONS ===\n"
    )

    for inv in tool_invocations:
        log_content += f"\n[CALL: {inv['command']}]\n"
        if inv.get("stdout"):
            log_content += f"stdout: {inv['stdout']}\n"
        if inv.get("stderr"):
            log_content += f"stderr: {inv['stderr']}\n"

    log_content += f"\n=== CLAUDE FINAL RESPONSE ===\n{final_text}"

    if stderr:
        log_content += f"\n\n=== STDERR ===\n{stderr}"
    if exit_code != 0:
        log_content += f"\n\n=== EXIT CODE ===\n{exit_code}"

    log.write_text(log_content, encoding="utf-8")
    return final_text


def _parse_stream_json(raw_output: str) -> tuple[list[dict[str, Any]], str]:
    """Parse stream-json output from claude --print to extract tool calls and final response.

    Returns:
        Tuple of (tool_invocations, final_response_text) where tool_invocations is a list
        of dicts with keys: 'tool', 'command', 'stdout', 'stderr', 'exit_code'
    """
    tool_invocations: list[dict[str, Any]] = []
    final_text = ""
    tool_id_map: dict[str, int] = {}  # Map tool_use_id to index in tool_invocations

    for line in raw_output.split("\n"):
        line = line.strip()
        if not line:
            continue

        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Extract tool_use objects (Bash invocations)
        if obj.get("type") == "assistant" and obj.get("message"):
            content = obj["message"].get("content", [])
            for item in content:
                if item.get("type") == "tool_use" and item.get("name") == "Bash":
                    cmd = item.get("input", {}).get("command", "")
                    tool_id = item.get("id", "")
                    if cmd:
                        idx = len(tool_invocations)
                        tool_invocations.append({
                            "tool": "Bash",
                            "command": cmd,
                            "stdout": "",
                            "stderr": "",
                            "exit_code": 0,
                        })
                        if tool_id:
                            tool_id_map[tool_id] = idx
                elif item.get("type") == "text":
                    final_text += item.get("text", "")

        # Extract tool results (stdout from bash commands)
        elif obj.get("type") == "user" and obj.get("message"):
            # Tool results can be in two places:
            # 1. Inside message.content[].tool_use_result (legacy)
            # 2. At the top level as tool_use_result
            tool_result = obj.get("tool_use_result")
            content = obj["message"].get("content", [])

            # Check for tool results in content array first
            for item in content:
                if item.get("type") == "tool_result":
                    tool_id = item.get("tool_use_id", "")
                    if tool_id in tool_id_map:
                        idx = tool_id_map[tool_id]
                        tool_invocations[idx]["stdout"] = item.get("content", "")
                        tool_invocations[idx]["stderr"] = ""

            # Then check top-level tool_use_result
            if tool_result and isinstance(tool_result, dict):
                stdout = tool_result.get("stdout", "")
                stderr = tool_result.get("stderr", "")
                if tool_invocations:
                    tool_invocations[-1]["stdout"] = stdout
                    tool_invocations[-1]["stderr"] = stderr

    return tool_invocations, final_text


def build_prompt(
    role: str,
    day: int,
    signal: dict[str, object],
    skill_file: str,
    state_context: str = "",
) -> str:
    """Assemble the prompt given to ``claude --print``.

    Parameters
    ----------
    state_context:
        Formatted state data to embed in the prompt.
        If provided, agent has current state without making API calls.
    """

    skill_text = Path(skill_file).read_text(encoding="utf-8")

    # Insert state context if provided
    state_section = f"{state_context}\n" if state_context else ""

    return (
        f"# Simulation turn — day {day}\n\n"
        f"{state_section}"
        f"## Your skill\n\n{skill_text}\n\n"
        f"## Market signal for day {day}\n\n"
        f"```json\n{signal}\n```\n\n"
        f"Follow the decision framework in your skill file.  "
        f"**Batch your commands** to reduce API calls: you can request multiple tool executions in one response.\n"
        f"When done, print your 3–5 bullet summary.\n"
    )
