"""Subprocess wrapper for ``claude --print`` agent invocations.

Phase 1 (deterministic): ``run_agent`` is given ``skill_file=None`` and
returns immediately with a stub log line.

Phase 2 (one agent): a non-None ``skill_file`` triggers a real
``claude --print`` subprocess.  The result is written to
``logs/day-{day:03d}-{role}.log`` and the stdout is returned.

Timeout behaviour: if ``claude --print`` exceeds ``timeout_seconds``, the
runner logs a ``[timeout]`` marker and returns the partial stdout.  A stuck
agent never freezes the simulation.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional


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
    """

    LOGS_DIR.mkdir(exist_ok=True)
    log = _log_path(day, role)

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
        if result.returncode != 0 and result.stderr:
            stdout += f"\n[stderr] {result.stderr.strip()}\n"
    except subprocess.TimeoutExpired as exc:
        partial = (exc.stdout or b"").decode("utf-8", errors="replace")
        stdout = partial + f"\n[timeout] {role} agent exceeded {timeout_seconds}s on day {day}\n"

    log.write_text(stdout, encoding="utf-8")
    return stdout


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
