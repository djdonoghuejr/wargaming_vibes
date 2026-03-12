from __future__ import annotations

from fastapi import BackgroundTasks
from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.api.jobs import JobRegistry
from apps.api.models import ActionAcceptedResponse
from apps.api.models import CatalogSummaryResponse
from apps.api.models import ComparisonDetailResponse
from apps.api.models import HealthResponse
from apps.api.models import InstantiateRequest
from apps.api.models import InstantiationDetailResponse
from apps.api.models import JobStatusResponse
from apps.api.models import ListResponse
from apps.api.models import RunBatchRequest
from apps.api.models import RunDetailResponse
from apps.api.models import TemplateDetailResponse
from apps.api.service import AnalystDataService
from apps.api.service import ApiSettings
from apps.api.service import CatalogUnavailableError
from apps.api.service import ResourceNotFoundError
from apps.api.service import default_api_settings
from oeg.workflows import instantiate_template_assets
from oeg.workflows import load_template_bundle
from oeg.workflows import run_batch_from_templates


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    api_settings = settings or default_api_settings()
    service = AnalystDataService(api_settings)
    job_registry = JobRegistry(api_settings.analysis_dir / "jobs")

    app = FastAPI(title="Operational Experiment Generator Analyst API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_service() -> AnalystDataService:
        return service

    def get_jobs() -> JobRegistry:
        return job_registry

    @app.exception_handler(CatalogUnavailableError)
    async def catalog_error_handler(_, exc: CatalogUnavailableError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(ResourceNotFoundError)
    async def not_found_handler(_, exc: ResourceNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.get("/health", response_model=HealthResponse)
    def health(current_service: AnalystDataService = Depends(get_service)) -> HealthResponse:
        return HealthResponse.model_validate(current_service.health())

    @app.get("/catalog/summary", response_model=CatalogSummaryResponse)
    def catalog_summary(current_service: AnalystDataService = Depends(get_service)) -> CatalogSummaryResponse:
        return CatalogSummaryResponse.model_validate(current_service.summary())

    @app.get("/templates", response_model=ListResponse)
    def list_templates(
        template_kind: str | None = Query(default=None),
        approval_state: str | None = Query(default=None),
        side: str | None = Query(default=None),
        doctrine: str | None = Query(default=None),
        base_asset_id: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        sort_by: str = Query(default="quality_score"),
        sort_dir: str = Query(default="desc"),
        current_service: AnalystDataService = Depends(get_service),
    ) -> ListResponse:
        return ListResponse.model_validate(
            current_service.list_templates(
                template_kind=template_kind,
                approval_state=approval_state,
                side=side,
                doctrine=doctrine,
                base_asset_id=base_asset_id,
                limit=limit,
                offset=offset,
                sort_by=sort_by,
                sort_dir=sort_dir,
            )
        )

    @app.get("/templates/{template_id}", response_model=TemplateDetailResponse)
    def get_template(
        template_id: str,
        current_service: AnalystDataService = Depends(get_service),
    ) -> TemplateDetailResponse:
        return TemplateDetailResponse.model_validate(current_service.get_template_detail(template_id))

    @app.get("/runs", response_model=ListResponse)
    def list_runs(
        scenario_id: str | None = Query(default=None),
        source_template_id: str | None = Query(default=None),
        seed: int | None = Query(default=None),
        stochastic_profile_id: str | None = Query(default=None),
        quality_band: str | None = Query(default=None),
        final_outcome: str | None = Query(default=None),
        blue_actor_id: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        sort_by: str = Query(default="run_id"),
        sort_dir: str = Query(default="desc"),
        current_service: AnalystDataService = Depends(get_service),
    ) -> ListResponse:
        return ListResponse.model_validate(
            current_service.list_runs(
                scenario_id=scenario_id,
                source_template_id=source_template_id,
                seed=seed,
                stochastic_profile_id=stochastic_profile_id,
                quality_band=quality_band,
                final_outcome=final_outcome,
                blue_actor_id=blue_actor_id,
                limit=limit,
                offset=offset,
                sort_by=sort_by,
                sort_dir=sort_dir,
            )
        )

    @app.get("/runs/{run_id}", response_model=RunDetailResponse)
    def get_run_detail(
        run_id: str,
        current_service: AnalystDataService = Depends(get_service),
    ) -> RunDetailResponse:
        return RunDetailResponse.model_validate(current_service.get_run_detail(run_id))

    @app.get("/runs/{run_id}/events", response_model=ListResponse)
    def get_run_events(
        run_id: str,
        turn: int | None = Query(default=None, ge=1),
        phase: str | None = Query(default=None),
        actor_side: str | None = Query(default=None),
        action_type: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        current_service: AnalystDataService = Depends(get_service),
    ) -> ListResponse:
        return ListResponse.model_validate(
            current_service.get_run_events(
                run_id,
                turn=turn,
                phase=phase,
                actor_side=actor_side,
                action_type=action_type,
                limit=limit,
                offset=offset,
            )
        )

    @app.get("/comparisons", response_model=ListResponse)
    def list_comparisons(
        limit: int = Query(default=20, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        sort_dir: str = Query(default="desc"),
        current_service: AnalystDataService = Depends(get_service),
    ) -> ListResponse:
        return ListResponse.model_validate(
            current_service.list_comparisons(limit=limit, offset=offset, sort_dir=sort_dir)
        )

    @app.get("/comparisons/{comparison_id}", response_model=ComparisonDetailResponse)
    def get_comparison_detail(
        comparison_id: str,
        current_service: AnalystDataService = Depends(get_service),
    ) -> ComparisonDetailResponse:
        return ComparisonDetailResponse.model_validate(current_service.get_comparison_detail(comparison_id))

    @app.get("/instantiations/{instantiation_id}", response_model=InstantiationDetailResponse)
    def get_instantiation_detail(
        instantiation_id: str,
        current_service: AnalystDataService = Depends(get_service),
    ) -> InstantiationDetailResponse:
        return InstantiationDetailResponse.model_validate(
            current_service.get_instantiation_detail(instantiation_id)
        )

    @app.get("/lessons", response_model=ListResponse)
    def list_lessons(
        tag: str | None = Query(default=None),
        condition: str | None = Query(default=None),
        scenario_id: str | None = Query(default=None),
        run_id: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        current_service: AnalystDataService = Depends(get_service),
    ) -> ListResponse:
        return ListResponse.model_validate(
            current_service.list_lessons(
                tag=tag,
                condition=condition,
                scenario_id=scenario_id,
                run_id=run_id,
                limit=limit,
                offset=offset,
            )
        )

    @app.post("/actions/instantiate", response_model=ActionAcceptedResponse)
    def action_instantiate(
        request: InstantiateRequest,
        background_tasks: BackgroundTasks,
        current_service: AnalystDataService = Depends(get_service),
        jobs: JobRegistry = Depends(get_jobs),
    ) -> ActionAcceptedResponse:
        job = jobs.create_job("instantiate", request.model_dump(mode="json"))

        def runner() -> dict[str, object]:
            paths = current_service.resolve_template_paths(
                scenario_template_id=request.scenario_template_id,
                blue_force_template_id=request.blue_force_template_id,
                red_force_template_id=request.red_force_template_id,
                blue_coa_template_ids=[request.blue_coa_template_id],
                red_coa_template_id=request.red_coa_template_id,
            )
            template_bundle = load_template_bundle(
                scenario_template_path=paths["scenario_template_path"],
                blue_force_template_path=paths["blue_force_template_path"],
                red_force_template_path=paths["red_force_template_path"],
                blue_coa_template_paths=paths["blue_coa_template_paths"],
                red_coa_template_path=paths["red_coa_template_path"],
            )
            result = instantiate_template_assets(
                template_bundle=template_bundle,
                seed=request.seed,
                sampling_profile=request.sampling_profile,
                output_dir=current_service.settings.generated_dir,
            )
            return {
                "instantiation_id": result.bundle.instantiation.id,
                "output_dir": str(result.output_dir),
                "scenario_id": result.bundle.scenario.id,
                "blue_force_package_id": result.bundle.blue_force.id,
                "red_force_package_id": result.bundle.red_force.id,
                "blue_coa_id": result.bundle.blue_coa.id,
                "red_coa_id": result.bundle.red_coa.id,
            }

        background_tasks.add_task(jobs.start_job, job, runner)
        return ActionAcceptedResponse(job_id=job.id, status=job.status)

    @app.post("/actions/run-batch", response_model=ActionAcceptedResponse)
    def action_run_batch(
        request: RunBatchRequest,
        background_tasks: BackgroundTasks,
        current_service: AnalystDataService = Depends(get_service),
        jobs: JobRegistry = Depends(get_jobs),
    ) -> ActionAcceptedResponse:
        job = jobs.create_job("run_batch", request.model_dump(mode="json"))

        def runner() -> dict[str, object]:
            paths = current_service.resolve_template_paths(
                scenario_template_id=request.scenario_template_id,
                blue_force_template_id=request.blue_force_template_id,
                red_force_template_id=request.red_force_template_id,
                blue_coa_template_ids=request.blue_coa_template_ids,
                red_coa_template_id=request.red_coa_template_id,
            )
            template_bundle = load_template_bundle(
                scenario_template_path=paths["scenario_template_path"],
                blue_force_template_path=paths["blue_force_template_path"],
                red_force_template_path=paths["red_force_template_path"],
                blue_coa_template_paths=paths["blue_coa_template_paths"],
                red_coa_template_path=paths["red_coa_template_path"],
            )
            result = run_batch_from_templates(
                template_bundle=template_bundle,
                seeds=request.seeds,
                sampling_profile=request.sampling_profile,
                output_dir=current_service.settings.runs_dir,
                catalog_path=current_service.settings.catalog_path,
                require_approved=request.require_approved,
            )
            return {
                "comparison_id": result.comparison.id,
                "run_ids": [path.name for path in result.run_dirs],
                "output_dir": str(result.comparison_dir),
            }

        background_tasks.add_task(jobs.start_job, job, runner)
        return ActionAcceptedResponse(job_id=job.id, status=job.status)

    @app.get("/actions/jobs/{job_id}", response_model=JobStatusResponse)
    def get_job_status(job_id: str, jobs: JobRegistry = Depends(get_jobs)) -> JobStatusResponse:
        job = jobs.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' was not found.")
        return job

    return app


app = create_app()
