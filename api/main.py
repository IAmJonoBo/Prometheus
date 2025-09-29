"""FastAPI surface for running Prometheus pipeline executions."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from uvicorn import run as uvicorn_run

from prometheus.pipeline import PrometheusOrchestrator

from .bootstrap import APISettingsError, get_orchestrator
from .serializers import to_serialisable


class PipelineRunRequest(BaseModel):
    """Input payload for triggering a pipeline run."""

    query: str = Field(
        ..., min_length=1, description="User query to drive retrieval and reasoning"
    )
    actor: str | None = Field(
        None, description="Optional actor identifier for auditing"
    )


class PipelineRunResponse(BaseModel):
    """Structured response containing pipeline artefacts."""

    result: dict[str, Any]


def create_app() -> FastAPI:
    """Instantiate the FastAPI application."""

    app = FastAPI(title="Prometheus Strategy OS API", version="0.1.0")

    @app.on_event("startup")
    async def ensure_orchestrator() -> None:  # pragma: no cover - defensive boot guard
        try:
            get_orchestrator()
        except (
            APISettingsError
        ) as exc:  # pragma: no cover - configuration errors surface on boot
            raise RuntimeError(str(exc)) from exc

    def orchestrator_dependency() -> PrometheusOrchestrator:
        try:
            return get_orchestrator()
        except APISettingsError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            ) from exc

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        """Return liveness heartbeat."""

        return {"status": "ok"}

    @app.post("/v1/pipeline/run", response_model=PipelineRunResponse, tags=["pipeline"])
    async def run_pipeline(request: PipelineRunRequest) -> PipelineRunResponse:
        """Execute the end-to-end pipeline and return structured artefacts."""

        orchestrator = orchestrator_dependency()
        result = orchestrator.run(query=request.query, actor=request.actor)
        return PipelineRunResponse(result=to_serialisable(result))

    return app


app = create_app()


def run() -> None:
    """Entry point for running the API with Uvicorn."""

    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))
    reload = os.getenv("API_RELOAD", "false").lower() in {"1", "true", "yes"}
    uvicorn_run("api.main:app", host=host, port=port, reload=reload)
