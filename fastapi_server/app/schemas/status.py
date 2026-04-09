from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DependencyStatus(BaseModel):
    status: Literal["ok", "disabled", "unhealthy"]
    detail: str | None = None


class SystemStatusResponse(BaseModel):
    status: Literal["ok", "degraded", "unhealthy"]
    env: str
    llm: DependencyStatus
    voice: DependencyStatus
    database: DependencyStatus
    tags: list[str] = Field(default_factory=list)
