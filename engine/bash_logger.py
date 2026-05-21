"""Logger for Bash tool invocations made by Claude agents.

Captures every bash command that Claude calls, with results.
Logs to JSONL format for easy parsing and analysis.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class BashLogger:
    """Log all Bash commands executed by Claude agents to JSONL."""

    def __init__(self, day: int, logs_dir: Path = Path("logs"), role: str | None = None) -> None:
        """Initialize logger for a specific day.

        Parameters
        ----------
        day:
            Simulation day number. Used in log filename.
        logs_dir:
            Directory to write logs to.
        """
        logs_dir.mkdir(exist_ok=True)
        self._path = logs_dir / f"day-{day:03d}-bash-calls.jsonl"
        self._day = day
        self._role = role

    def log(
        self,
        command: str,
        stdout: str,
        stderr: str = "",
        exit_code: int = 0,
    ) -> None:
        """Log a bash command invocation.

        Parameters
        ----------
        command:
            The bash command that was run
        stdout:
            Output from the command
        stderr:
            Error output (if any)
        exit_code:
            Exit code from the command
        """
        entry = {
            "ts": datetime.utcnow().isoformat(),
            "day": self._day,
            "role": self._role,
            "command": command,
            "exit_code": exit_code,
            "stdout": stdout[:500].strip() if stdout else "",
            "stderr": stderr[:200].strip() if stderr else None,
        }
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
