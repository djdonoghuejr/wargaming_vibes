from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from pydantic import Field


class HealthResponse(BaseModel):
    status: str
    catalog_path: str
    catalog_exists: bool


class CatalogSummaryResponse(BaseModel):
    catalog_path: str
    counts: dict[str, int]
    recent_runs: list[dict[str, Any]] = Field(default_factory=list)
    recent_comparisons: list[dict[str, Any]] = Field(default_factory=list)
    recent_templates: list[dict[str, Any]] = Field(default_factory=list)


class ListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[dict[str, Any]]


class RunDetailResponse(BaseModel):
    manifest: dict[str, Any]
    scenario: dict[str, Any] | None = None
    final_state: dict[str, Any] | None = None
    aar: dict[str, Any] | None = None
    lessons: list[dict[str, Any]] = Field(default_factory=list)
    instantiation: dict[str, Any] | None = None
    event_summary: dict[str, Any] = Field(default_factory=dict)


class TemplateDetailResponse(BaseModel):
    summary: dict[str, Any]
    raw_template: dict[str, Any]
    related_runs: list[dict[str, Any]] = Field(default_factory=list)
    related_comparisons: list[dict[str, Any]] = Field(default_factory=list)


class ComparisonDetailResponse(BaseModel):
    comparison: dict[str, Any]
    metric_rows: list[dict[str, Any]] = Field(default_factory=list)
    linked_runs: list[dict[str, Any]] = Field(default_factory=list)


class InstantiationDetailResponse(BaseModel):
    instantiation: dict[str, Any]
    scenario: dict[str, Any]
    blue_force: dict[str, Any]
    red_force: dict[str, Any]
    blue_coa: dict[str, Any]
    red_coa: dict[str, Any]


class InstantiateRequest(BaseModel):
    scenario_template_id: str
    blue_force_template_id: str
    red_force_template_id: str
    blue_coa_template_id: str
    red_coa_template_id: str
    seed: int = Field(ge=0)
    sampling_profile: str = "hybrid_stochastic_v1"


class RunBatchRequest(BaseModel):
    scenario_template_id: str
    blue_force_template_id: str
    red_force_template_id: str
    blue_coa_template_ids: list[str] = Field(min_length=1)
    red_coa_template_id: str
    seeds: list[int] = Field(min_length=1)
    sampling_profile: str = "hybrid_stochastic_v1"
    require_approved: bool = True


class ActionAcceptedResponse(BaseModel):
    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    id: str
    job_type: str
    status: str
    submitted_at: str
    started_at: str | None = None
    completed_at: str | None = None
    request_payload: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
