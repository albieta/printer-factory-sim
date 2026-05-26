"""REST endpoints for launching scenario runs and tailing engine logs."""

from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.scenario_runner import LOGS_DIR, scenario_runner


router = APIRouter()


class ScenarioStartRequest(BaseModel):
    config: str = Field(..., description="Filename of config under config/")
    scenario: str = Field(..., description="Filename of scenario under scenarios/")
    days: int = Field(..., ge=1, le=60, description="Number of simulated days to run")
    model: str = Field(default="claude-haiku-4-5-20251001", description="Claude model to use for agents")
    thinking_enabled: bool = Field(default=False, description="Whether to enable extended thinking")
    assembly_lines: int = Field(default=1, ge=1, le=20, description="Number of parallel assembly lines")
    workers_per_line: int = Field(default=1, ge=1, le=20, description="Workers per assembly line")
    shift_hours: float = Field(default=8.0, ge=1.0, le=24.0, description="Hours worked per shift")
    fast_mode: bool = Field(default=False, description="Replace LLM agents with scripted deterministic logic (~60x faster, no API cost)")


@router.get("/")
def list_scenarios() -> dict[str, Any]:
    return {
        "scenarios": scenario_runner.list_scenarios(),
        "configs": scenario_runner.list_configs(),
    }


@router.get("/status")
def get_status() -> dict[str, Any]:
    record = scenario_runner.status()
    return {"active": record is not None and record.get("status") == "running", "run": record}


@router.post("/start")
def start_scenario(payload: ScenarioStartRequest) -> dict[str, Any]:
    try:
        return scenario_runner.start(
            payload.config,
            payload.scenario,
            payload.days,
            model=payload.model,
            thinking_enabled=payload.thinking_enabled,
            assembly_lines=payload.assembly_lines,
            workers_per_line=payload.workers_per_line,
            shift_hours=payload.shift_hours,
            fast_mode=payload.fast_mode,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/stop")
def stop_scenario() -> dict[str, Any]:
    return scenario_runner.stop()


@router.get("/logs")
def list_logs() -> dict[str, Any]:
    return {"files": scenario_runner.list_log_files()}


@router.get("/logs/{name}")
def get_log(name: str, max_bytes: int = Query(64 * 1024, ge=1, le=1024 * 1024)) -> dict[str, Any]:
    try:
        return scenario_runner.tail_log(name, max_bytes=max_bytes)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/metrics")
def get_metrics(limit: int = Query(100, ge=1, le=1000)) -> dict[str, Any]:
    return {"snapshots": scenario_runner.read_metrics(limit=limit)}


@router.post("/logs/clear")
def clear_logs() -> dict[str, Any]:
    return scenario_runner.clear_logs()


@router.get("/logs/download")
def download_logs() -> StreamingResponse:
    """Stream all log files as a ZIP archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        if LOGS_DIR.exists():
            for entry in sorted(LOGS_DIR.iterdir()):
                if entry.is_file():
                    zf.write(entry, arcname=entry.name)
    buf.seek(0)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"simulation-logs-{ts}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
