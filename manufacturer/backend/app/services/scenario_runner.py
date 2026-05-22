"""Background scenario runner for the visual interface.

Spawns ``python -m engine.turn_engine <config> <scenario> <days>`` as a
subprocess and exposes its progress through small read-only helpers so the
React app can poll status, summaries, and per-agent logs while the
simulation is running.

Design notes
------------
* Only one run is allowed at a time. This matches the engine, which
  drives the three live apps and shares simulation state with them.
* Run state is kept in-memory. A restart of the manufacturer backend
  drops the handle — the underlying logs and metrics file on disk are
  still available for inspection.
* Path resolution always anchors to the repository root (four parents up
  from this file) so subprocesses see the same ``logs/`` directory the
  engine writes to.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

# manufacturer/backend/app/services/scenario_runner.py -> repo root
PROJECT_ROOT: Path = Path(__file__).resolve().parents[4]
SCENARIOS_DIR: Path = PROJECT_ROOT / "scenarios"
CONFIGS_DIR: Path = PROJECT_ROOT / "config"
LOGS_DIR: Path = PROJECT_ROOT / "logs"
METRICS_FILE: Path = LOGS_DIR / "metrics.jsonl"
VENV_PYTHON: Path = PROJECT_ROOT / ".venv" / "bin" / "python"


@dataclass
class RunRecord:
    """Snapshot of a scenario run, exposed verbatim via the API."""

    run_id: str
    config: str
    scenario: str
    days: int
    started_at: str
    status: str = "running"
    finished_at: Optional[str] = None
    exit_code: Optional[int] = None
    stdout_lines: list[str] = field(default_factory=list)
    log_file: Optional[str] = None
    current_day: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ScenarioRunner:
    """Manage a single background scenario subprocess."""

    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen[str]] = None
        self._record: Optional[RunRecord] = None
        self._lock = threading.Lock()
        self._reader_thread: Optional[threading.Thread] = None

    # ── public API ───────────────────────────────────────────────────────

    def list_scenarios(self) -> list[dict[str, Any]]:
        """Return scenario JSON files with a brief summary for each."""
        return [self._summarize_json(path, kind="scenario") for path in self._iter_json(SCENARIOS_DIR)]

    def list_configs(self) -> list[dict[str, Any]]:
        """Return config JSON files with a brief summary for each."""
        return [self._summarize_json(path, kind="config") for path in self._iter_json(CONFIGS_DIR)]

    def status(self) -> Optional[dict[str, Any]]:
        """Return the current run's status dict, or ``None`` if no run yet."""
        with self._lock:
            if self._record is None:
                return None
            return self._record.to_dict()

    def start(
        self,
        config_name: str,
        scenario_name: str,
        days: int,
        model: str = "claude-haiku-4-5-20251001",
        thinking_enabled: bool = False,
        assembly_lines: int = 1,
        workers_per_line: int = 1,
        shift_hours: float = 8.0,
    ) -> dict[str, Any]:
        """Launch a scenario run in the background.

        Raises
        ------
        FileNotFoundError
            If the named scenario or config file does not exist.
        RuntimeError
            If another run is already in progress.
        ValueError
            If ``days`` is out of range.
        """

        if days < 1 or days > 60:
            raise ValueError("days must be between 1 and 60")

        config_path = self._resolve_under(CONFIGS_DIR, config_name)
        scenario_path = self._resolve_under(SCENARIOS_DIR, scenario_name)
        if not config_path.exists():
            raise FileNotFoundError(f"config not found: {config_name}")
        if not scenario_path.exists():
            raise FileNotFoundError(f"scenario not found: {scenario_name}")

        with self._lock:
            if self._process and self._process.poll() is None:
                raise RuntimeError("a scenario run is already in progress")

            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            run_id = datetime.now(timezone.utc).strftime("run-%Y%m%d-%H%M%S")
            stdout_log = LOGS_DIR / f"{run_id}.log"
            self._record = RunRecord(
                run_id=run_id,
                config=str(config_path.relative_to(PROJECT_ROOT)),
                scenario=str(scenario_path.relative_to(PROJECT_ROOT)),
                days=days,
                started_at=datetime.now(timezone.utc).isoformat(),
                log_file=str(stdout_log.relative_to(PROJECT_ROOT)),
            )

            python_bin = str(VENV_PYTHON) if VENV_PYTHON.exists() else "python3"
            cmd = [
                python_bin,
                "-m",
                "engine.turn_engine",
                str(config_path),
                str(scenario_path),
                str(days),
            ]
            # Unbuffered output so the UI sees progress without delays.
            env = os.environ.copy()
            env.setdefault("PYTHONUNBUFFERED", "1")
            env["CLAUDE_MODEL"] = model
            env["CLAUDE_THINKING_ENABLED"] = "true" if thinking_enabled else "false"
            env["ASSEMBLY_LINES"] = str(assembly_lines)
            env["WORKERS_PER_LINE"] = str(workers_per_line)
            env["SHIFT_HOURS"] = str(shift_hours)

            self._process = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )

            self._reader_thread = threading.Thread(
                target=self._tail_process,
                args=(self._process, self._record, stdout_log),
                daemon=True,
            )
            self._reader_thread.start()
            return self._record.to_dict()

    def stop(self) -> dict[str, Any]:
        """Best-effort termination of the active run."""
        with self._lock:
            if self._process is None or self._process.poll() is not None:
                return {"stopped": False, "reason": "no active run"}
            try:
                self._process.send_signal(signal.SIGTERM)
            except Exception:
                pass
            if self._record:
                self._record.status = "stopping"
            return {"stopped": True}

    def tail_log(self, name: str, max_bytes: int = 64 * 1024) -> dict[str, Any]:
        """Return the tail of a log file as plain text (path-safe)."""
        log_path = self._resolve_under(LOGS_DIR, name)
        if not log_path.exists():
            return {"name": name, "exists": False, "content": ""}
        size = log_path.stat().st_size
        with log_path.open("rb") as handle:
            if size > max_bytes:
                handle.seek(-max_bytes, os.SEEK_END)
            data = handle.read()
        return {
            "name": name,
            "exists": True,
            "size": size,
            "truncated": size > max_bytes,
            "content": data.decode("utf-8", errors="replace"),
        }

    def list_log_files(self) -> list[dict[str, Any]]:
        """List all files in ``logs/`` with size and mtime."""
        if not LOGS_DIR.exists():
            return []
        files = []
        for entry in sorted(LOGS_DIR.iterdir()):
            if not entry.is_file():
                continue
            stat = entry.stat()
            files.append(
                {
                    "name": entry.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                }
            )
        return files

    def read_metrics(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return up to ``limit`` most-recent metric snapshots from JSONL."""
        if not METRICS_FILE.exists():
            return []
        lines = METRICS_FILE.read_text(encoding="utf-8").splitlines()
        if limit > 0:
            lines = lines[-limit:]
        out: list[dict[str, Any]] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def clear_logs(self) -> dict[str, Any]:
        """Remove every file in ``logs/`` (does not refuse if a run is active)."""
        if not LOGS_DIR.exists():
            return {"deleted": 0}
        deleted = 0
        for entry in LOGS_DIR.iterdir():
            if entry.is_file():
                try:
                    entry.unlink()
                    deleted += 1
                except OSError:
                    continue
        return {"deleted": deleted}

    # ── internals ────────────────────────────────────────────────────────

    def _tail_process(
        self,
        process: subprocess.Popen[str],
        record: RunRecord,
        log_path: Path,
    ) -> None:
        """Drain subprocess stdout into the record and a log file."""
        try:
            with log_path.open("w", encoding="utf-8") as handle:
                if process.stdout is None:
                    return
                for raw in process.stdout:
                    line = raw.rstrip("\n")
                    handle.write(raw)
                    handle.flush()
                    with self._lock:
                        record.stdout_lines.append(line)
                        # Keep memory bounded.
                        if len(record.stdout_lines) > 2000:
                            del record.stdout_lines[:1000]
                        if line.startswith("=== Day "):
                            try:
                                record.current_day = int(line.split("Day ", 1)[1].split(" ", 1)[0])
                            except (IndexError, ValueError):
                                pass
        finally:
            exit_code = process.wait()
            with self._lock:
                record.exit_code = exit_code
                record.finished_at = datetime.now(timezone.utc).isoformat()
                record.status = "completed" if exit_code == 0 else "failed"

    @staticmethod
    def _iter_json(folder: Path) -> Iterable[Path]:
        if not folder.exists():
            return []
        return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix == ".json")

    @staticmethod
    def _summarize_json(path: Path, *, kind: str) -> dict[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        summary: dict[str, Any] = {
            "name": path.name,
            "relative_path": str(path.relative_to(PROJECT_ROOT)),
            "kind": kind,
        }
        if kind == "scenario":
            summary.update(
                {
                    "scenario_name": data.get("scenario_name"),
                    "event_count": len(data.get("events", [])),
                    "events": [
                        {
                            "name": event.get("name"),
                            "start_day": event.get("start_day"),
                            "end_day": event.get("end_day"),
                            "description": event.get("description"),
                        }
                        for event in data.get("events", [])
                        if isinstance(event, dict)
                    ],
                }
            )
            if data.get("recommended_assembly"):
                summary["recommended_assembly"] = data.get("recommended_assembly")
            if data.get("recommended_costs"):
                summary["recommended_costs"] = data.get("recommended_costs")
        else:  # config
            skill_flags: list[bool] = []
            if isinstance(data, dict):
                skill_flags.append(bool((data.get("manufacturer") or {}).get("skill")))
                for entry in data.get("retailers", []):
                    if isinstance(entry, dict):
                        skill_flags.append(bool(entry.get("skill")))
                for entry in data.get("providers", []):
                    if isinstance(entry, dict):
                        skill_flags.append(bool(entry.get("skill")))
            summary.update(
                {
                    "retailers": [r.get("name") for r in data.get("retailers", []) if isinstance(r, dict)],
                    "manufacturer": (data.get("manufacturer") or {}).get("name"),
                    "providers": [p.get("name") for p in data.get("providers", []) if isinstance(p, dict)],
                    "uses_skills": any(skill_flags),
                }
            )
        return summary

    @staticmethod
    def _resolve_under(base: Path, name: str) -> Path:
        """Resolve ``name`` under ``base`` rejecting any path traversal."""
        candidate = (base / name).resolve()
        try:
            candidate.relative_to(base.resolve())
        except ValueError as exc:
            raise FileNotFoundError(name) from exc
        return candidate


# Process-wide singleton — the API endpoints share this instance.
scenario_runner = ScenarioRunner()
