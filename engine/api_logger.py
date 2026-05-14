"""API call logger for turn engine — records all HTTP requests/responses to JSONL."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class ApiLogger:
    """Log all HTTP calls made during a simulation day to a JSONL file."""

    def __init__(self, day: int, logs_dir: Path = Path("logs")) -> None:
        """Initialize logger for a specific day.

        Parameters
        ----------
        day:
            Simulation day number. Used in log filename (day-NNN-api-calls.jsonl).
        logs_dir:
            Directory to write logs to. Created if missing.
        """
        logs_dir.mkdir(exist_ok=True)
        self._path = logs_dir / f"day-{day:03d}-api-calls.jsonl"
        self._day = day

    def log(
        self,
        method: str,
        url: str,
        request_body: dict[str, Any] | None,
        response_status: int,
        response_body: dict[str, Any],
    ) -> None:
        """Log an HTTP call as a JSON line.

        Parameters
        ----------
        method:
            HTTP method (GET, POST, etc.)
        url:
            Full URL called
        request_body:
            Request JSON body (None for GET)
        response_status:
            HTTP status code
        response_body:
            Response JSON body
        """
        entry = {
            "ts": datetime.utcnow().isoformat(),
            "day": self._day,
            "method": method,
            "url": url,
            "request": request_body,
            "status": response_status,
            "response": str(response_body)[:500],  # truncate to 500 chars for readability
        }
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
