"""Subprocess wrapper for ``claude --print`` agent invocations.

Phase 1 (deterministic): ``run_agent`` is given ``skill_file=None`` and
returns immediately with a stub log line.

Phase 2 (one agent): a non-None ``skill_file`` triggers a real
``claude --print`` subprocess.  The result is written to
``logs/day-{day:03d}-{role}.log`` with complete flow:
  - Full prompt sent to Claude
  - Complete Claude output (includes reasoning + tool calls)
  - All stderr/warnings

Bash invocations are also logged separately to
``logs/day-{day:03d}-bash-calls.jsonl`` for visibility.

Timeout behaviour: if ``claude --print`` exceeds ``timeout_seconds``, the
runner logs a ``[timeout]`` marker and returns the partial stdout.  A stuck
agent never freezes the simulation.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional

from engine.bash_logger import BashLogger


LOGS_DIR = Path("logs")
DEFAULT_TIMEOUT = 180


def _log_path(day: int, role: str) -> Path:
    return LOGS_DIR / f"day-{day:03d}-{role}.log"


def run_agent(
    role: str,
    day: int,
    prompt: str,
    skill_file: Optional[str],
    cwd: str = ".",
    timeout_seconds: int = DEFAULT_TIMEOUT,
) -> str:
    """Run the agent for *role* on *day* and return its output.

    If *skill_file* is ``None``, the stub path is taken: no subprocess is
    spawned and a single-line marker is written to the log.

    Log format: for skill_file agents, logs complete flow:
    1. Full prompt sent to Claude
    2. Complete Claude output (reasoning + tool calls + results)
    3. All stderr/warnings
    4. Bash commands also logged to separate JSONL file
    """

    LOGS_DIR.mkdir(exist_ok=True)
    log = _log_path(day, role)
    bash_logger = BashLogger(day) if role == "Factory" else None

    if skill_file is None:
        output = f"[stub] {role} would decide here (day {day})\n"
        log.write_text(output, encoding="utf-8")
        return output

    try:
        result = subprocess.run(
            [
                "claude",
                "--print",
                "--permission-mode",
                "bypassPermissions",
                "--allowedTools",
                "Bash",
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
        stdout = result.stdout
        stderr = result.stderr or ""
        exit_code = result.returncode
    except subprocess.TimeoutExpired as exc:
        partial = (exc.stdout or b"").decode("utf-8", errors="replace")
        stdout = partial + f"\n[timeout] {role} agent exceeded {timeout_seconds}s on day {day}\n"
        stderr = ""
        exit_code = 124

    # Extract and log bash commands if logger exists
    if bash_logger:
        bash_calls = _extract_bash_calls(stdout)
        for call in bash_calls:
            bash_logger.log(
                command=call["command"],
                stdout=call["output"],
                stderr="",
                exit_code=0,
            )

    # Build complete log showing flow: prompt → reasoning → tool calls → response
    log_content = (
        "=== PROMPT SENT TO CLAUDE ===\n"
        f"{prompt}\n\n"
        "=== CLAUDE COMPLETE OUTPUT ===\n"
        f"{stdout}"
    )
    if stderr:
        log_content += f"\n\n=== STDERR ===\n{stderr}"
    if exit_code != 0:
        log_content += f"\n\n=== EXIT CODE ===\n{exit_code}"

    log.write_text(log_content, encoding="utf-8")
    return stdout


def _extract_bash_calls(output: str) -> list[dict[str, str]]:
    """Extract bash tool calls from Claude's output text.

    Looks for bash command invocations in the output and returns list of calls.
    Returns list of dicts with 'command' and 'output' keys.
    """
    calls = []
    # Simple regex to find bash commands in Claude's output
    # Pattern: looks for command text followed by output
    lines = output.split("\n")
    current_cmd = None
    current_output = []

    for line in lines:
        if "$ " in line or line.startswith("bin/"):
            if current_cmd:
                calls.append({
                    "command": current_cmd,
                    "output": "\n".join(current_output),
                })
            current_cmd = line.strip()
            current_output = []
        elif current_cmd:
            current_output.append(line)

    if current_cmd:
        calls.append({
            "command": current_cmd,
            "output": "\n".join(current_output),
        })

    return calls


def build_prompt(
    role: str,
    day: int,
    signal: dict[str, object],
    skill_file: str,
) -> str:
    """Assemble the prompt given to ``claude --print``."""

    skill_text = Path(skill_file).read_text(encoding="utf-8")
    return (
        f"# Simulation turn — day {day}\n\n"
        f"## Your skill\n\n{skill_text}\n\n"
        f"## Market signal for day {day}\n\n"
        f"```json\n{signal}\n```\n\n"
        f"Follow the decision framework in your skill file.  "
        f"When done, print your 3–5 bullet summary.\n"
    )
