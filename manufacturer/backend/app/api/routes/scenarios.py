"""REST endpoints for launching scenario runs and tailing engine logs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.scenario_runner import scenario_runner


router = APIRouter()


class ScenarioStartRequest(BaseModel):
    config: str = Field(..., description="Filename of config under config/")
    scenario: str = Field(..., description="Filename of scenario under scenarios/")
    days: int = Field(..., ge=1, le=60, description="Number of simulated days to run")
    model: str = Field(default="claude-haiku-4-5-20251001", description="Claude model to use for agents")
    thinking_enabled: bool = Field(default=False, description="Whether to enable extended thinking")


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
