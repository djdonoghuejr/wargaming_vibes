import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";

import { apiGet, apiPost, queryString } from "./api";
import {
  ApprovalPill,
  DataTable,
  EmptyState,
  ErrorState,
  EventTimeline,
  EvidenceChips,
  KeyValueGrid,
  LoadingState,
  MetricCard,
  OperationalGraph,
  OutcomePill,
  Panel,
  QualityPill,
  ScoreBar,
  StatusPill
} from "./components";

type ListResponse<T = any> = {
  total: number;
  limit: number;
  offset: number;
  items: T[];
};

type JobStatus = {
  id: string;
  status: string;
  result?: Record<string, any> | null;
  error?: string | null;
};

export function OverviewPage() {
  const summaryQuery = useQuery({
    queryKey: ["catalog-summary"],
    queryFn: () => apiGet<any>("/catalog/summary")
  });

  if (summaryQuery.isLoading) {
    return <LoadingState label="Loading overview" />;
  }

  if (summaryQuery.isError || !summaryQuery.data) {
    return (
      <ErrorState
        title="Catalog unavailable"
        detail={`Unable to load the analyst summary. ${String(summaryQuery.error)}`}
      />
    );
  }

  const { counts, recent_runs, recent_comparisons, recent_templates } = summaryQuery.data;

  return (
    <div className="page-stack">
      <div className="hero-metrics">
        <MetricCard label="Approved Templates" value={counts.approved_templates} note="Ready for batch execution" />
        <MetricCard label="Runs" value={counts.runs} note="Cataloged experimental realizations" />
        <MetricCard label="Comparisons" value={counts.comparisons} note="Paired-seed COA studies" />
        <MetricCard label="Lessons" value={counts.lessons} note="Evidence-linked analytical takeaways" />
      </div>

      <div className="split-grid">
        <Panel title="Recent Comparisons" subtitle="Latest recommendation snapshots">
          <DataTable
            keyField="comparison_id"
            rows={recent_comparisons}
            columns={[
              {
                key: "comparison_id",
                label: "Comparison",
                render: (row) => <Link to={`/comparisons/${row.comparison_id}`}>{row.comparison_id}</Link>
              },
              { key: "scenario_id", label: "Scenario" },
              {
                key: "recommended_coa",
                label: "Recommendation",
                render: (row) => <StatusPill tone="good">{row.recommended_coa}</StatusPill>
              },
              { key: "sample_count", label: "Samples" },
              {
                key: "confidence",
                label: "Confidence",
                render: (row) => `${Math.round((row.confidence ?? 0) * 100)}%`
              }
            ]}
          />
        </Panel>
        <Panel title="Recent Approved Templates" subtitle="Highest-value reusable assets">
          <DataTable
            keyField="template_id"
            rows={recent_templates}
            columns={[
              {
                key: "template_id",
                label: "Template",
                render: (row) => <Link to={`/templates/${row.template_id}`}>{row.template_id}</Link>
              },
              { key: "template_kind", label: "Kind" },
              {
                key: "approval_state",
                label: "Approval",
                render: (row) => <ApprovalPill value={row.approval_state} />
              },
              {
                key: "quality_score",
                label: "Score",
                render: (row) => `${Math.round((row.quality_score ?? 0) * 100)}%`
              }
            ]}
          />
        </Panel>
      </div>

      <Panel title="Recent Runs" subtitle="Quick access to current experimental traffic">
        <DataTable
          keyField="run_id"
          rows={recent_runs}
          columns={[
            {
              key: "run_id",
              label: "Run",
              render: (row) => <Link to={`/runs/${row.run_id}`}>{row.run_id}</Link>
            },
            { key: "scenario_id", label: "Scenario" },
            {
              key: "final_outcome",
              label: "Outcome",
              render: (row) => <OutcomePill value={row.final_outcome} />
            },
            {
              key: "blue_overall_score",
              label: "Blue",
              render: (row) => toPercent(row.blue_overall_score)
            },
            {
              key: "red_overall_score",
              label: "Red",
              render: (row) => toPercent(row.red_overall_score)
            },
            {
              key: "quality_band",
              label: "Quality",
              render: (row) => <QualityPill value={row.quality_band} />
            }
          ]}
        />
      </Panel>
    </div>
  );
}

export function TemplatesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const templateKind = searchParams.get("template_kind") ?? "";
  const approvalState = searchParams.get("approval_state") ?? "approved_for_batch";
  const side = searchParams.get("side") ?? "";
  const doctrine = searchParams.get("doctrine") ?? "";
  const baseAssetId = searchParams.get("base_asset_id") ?? "";

  const query = useQuery({
    queryKey: ["templates", templateKind, approvalState, side, doctrine, baseAssetId],
    queryFn: () =>
      apiGet<ListResponse>(
        `/templates${queryString({
          template_kind: templateKind || null,
          approval_state: approvalState || null,
          side: side || null,
          doctrine: doctrine || null,
          base_asset_id: baseAssetId || null,
          limit: 50
        })}`
      )
  });

  return (
    <div className="page-stack">
      <Panel title="Templates Explorer" subtitle="Filter reusable scenario, force, and COA assets">
        <div className="filter-grid">
          <FilterField label="Kind">
            <select value={templateKind} onChange={(event) => updateSearch(setSearchParams, "template_kind", event.target.value)}>
              <option value="">All</option>
              <option value="scenario_template">Scenario</option>
              <option value="force_template">Force</option>
              <option value="coa_template">COA</option>
            </select>
          </FilterField>
          <FilterField label="Approval">
            <select value={approvalState} onChange={(event) => updateSearch(setSearchParams, "approval_state", event.target.value)}>
              <option value="">All</option>
              <option value="approved_for_batch">Approved</option>
              <option value="promoted">Promoted</option>
              <option value="quarantined">Quarantined</option>
            </select>
          </FilterField>
          <FilterField label="Side">
            <select value={side} onChange={(event) => updateSearch(setSearchParams, "side", event.target.value)}>
              <option value="">Any</option>
              <option value="blue">Blue</option>
              <option value="red">Red</option>
            </select>
          </FilterField>
          <FilterField label="Doctrine">
            <input value={doctrine} onChange={(event) => updateSearch(setSearchParams, "doctrine", event.target.value)} placeholder="delay_defense" />
          </FilterField>
          <FilterField label="Base Asset">
            <input value={baseAssetId} onChange={(event) => updateSearch(setSearchParams, "base_asset_id", event.target.value)} placeholder="scn_corridor_001" />
          </FilterField>
        </div>
      </Panel>

      {query.isLoading ? <LoadingState label="Loading templates" /> : null}
      {query.isError ? <ErrorState title="Template query failed" detail={String(query.error)} /> : null}
      {query.data ? (
        <Panel
          title="Template Results"
          subtitle={`${query.data.total} matching templates`}
          actions={<StatusPill tone="info">Server-filtered</StatusPill>}
        >
          <DataTable
            keyField="template_id"
            rows={query.data.items}
            columns={[
              {
                key: "template_id",
                label: "Template",
                render: (row) => <Link to={`/templates/${row.template_id}`}>{row.template_id}</Link>
              },
              { key: "template_kind", label: "Kind" },
              { key: "side", label: "Side" },
              { key: "doctrine", label: "Doctrine" },
              { key: "base_asset_id", label: "Base Asset" },
              {
                key: "approval_state",
                label: "Approval",
                render: (row) => <ApprovalPill value={row.approval_state} />
              },
              {
                key: "quality_band",
                label: "Quality",
                render: (row) => <QualityPill value={row.quality_band} />
              },
              {
                key: "warning_count",
                label: "Warnings",
                render: (row) => row.warning_count ?? 0
              }
            ]}
          />
        </Panel>
      ) : null}
    </div>
  );
}

export function TemplateDetailPage() {
  const { templateId } = useParams();
  const query = useQuery({
    queryKey: ["template", templateId],
    queryFn: () => apiGet<any>(`/templates/${templateId}`),
    enabled: Boolean(templateId)
  });

  if (query.isLoading) {
    return <LoadingState label="Loading template detail" />;
  }

  if (query.isError || !query.data) {
    return <ErrorState title="Template detail unavailable" detail={String(query.error)} />;
  }

  const { summary, raw_template, related_runs, related_comparisons } = query.data;
  const variability = describeTemplateVariability(raw_template, summary.template_kind);

  return (
    <div className="page-stack">
      <Panel
        title={summary.name ?? summary.template_id}
        subtitle={summary.description ?? summary.template_kind}
        actions={<ApprovalPill value={summary.approval_state} />}
      >
        <div className="detail-stat-grid">
          <MetricCard label="Template ID" value={summary.template_id} />
          <MetricCard label="Kind" value={summary.template_kind} />
          <MetricCard label="Base Asset" value={summary.base_asset_id ?? "--"} />
          <MetricCard label="Quality" value={summary.quality_band ?? "--"} note={toPercent(summary.quality_score)} />
        </div>
      </Panel>

      <div className="split-grid">
        <Panel title="Variability Profile" subtitle="What this template can change across realizations">
          {variability.length ? (
            <div className="tag-list">
              {variability.map((item) => (
                <span key={item} className="reason-chip">
                  {item}
                </span>
              ))}
            </div>
          ) : (
            <EmptyState title="No variability summary available" />
          )}
          {(summary.warnings ?? []).length ? (
            <div className="warning-list">
              {(summary.warnings ?? []).map((warning: string) => (
                <div key={warning} className="warning-item">
                  {warning}
                </div>
              ))}
            </div>
          ) : (
            <div className="muted-copy">No quality warnings were recorded for this template.</div>
          )}
        </Panel>
        <Panel title="Downstream Usage" subtitle="Where this template already shows up">
          <div className="usage-stack">
            <div>
              <div className="section-label">Related Runs</div>
              <DataTable
                keyField="run_id"
                rows={related_runs}
                columns={[
                  {
                    key: "run_id",
                    label: "Run",
                    render: (row) => <Link to={`/runs/${row.run_id}`}>{row.run_id}</Link>
                  },
                  {
                    key: "final_outcome",
                    label: "Outcome",
                    render: (row) => <OutcomePill value={row.final_outcome} />
                  },
                  {
                    key: "quality_band",
                    label: "Quality",
                    render: (row) => <QualityPill value={row.quality_band} />
                  }
                ]}
              />
            </div>
            <div>
              <div className="section-label">Related Comparisons</div>
              <DataTable
                keyField="comparison_id"
                rows={related_comparisons}
                columns={[
                  {
                    key: "comparison_id",
                    label: "Comparison",
                    render: (row) => <Link to={`/comparisons/${row.comparison_id}`}>{row.comparison_id}</Link>
                  },
                  { key: "recommended_coa", label: "Recommendation" },
                  {
                    key: "confidence",
                    label: "Confidence",
                    render: (row) => toPercent(row.confidence)
                  }
                ]}
              />
            </div>
          </div>
        </Panel>
      </div>

      <Panel title="Raw Template Snapshot" subtitle="Structured source data preserved from generation">
        <pre className="json-panel">{JSON.stringify(raw_template, null, 2)}</pre>
      </Panel>
    </div>
  );
}

export function RunsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = {
    scenario_id: searchParams.get("scenario_id") ?? "",
    source_template_id: searchParams.get("source_template_id") ?? "",
    stochastic_profile_id: searchParams.get("stochastic_profile_id") ?? "",
    quality_band: searchParams.get("quality_band") ?? "",
    final_outcome: searchParams.get("final_outcome") ?? "",
    blue_actor_id: searchParams.get("blue_actor_id") ?? "",
    seed: searchParams.get("seed") ?? ""
  };

  const query = useQuery({
    queryKey: ["runs", filters],
    queryFn: () =>
      apiGet<ListResponse>(
        `/runs${queryString({
          scenario_id: filters.scenario_id || null,
          source_template_id: filters.source_template_id || null,
          stochastic_profile_id: filters.stochastic_profile_id || null,
          quality_band: filters.quality_band || null,
          final_outcome: filters.final_outcome || null,
          blue_actor_id: filters.blue_actor_id || null,
          seed: filters.seed || null,
          limit: 50
        })}`
      )
  });

  return (
    <div className="page-stack">
      <Panel title="Runs Explorer" subtitle="Filter realized experiments across lineage, seed, and quality">
        <div className="filter-grid">
          <FilterField label="Scenario">
            <input value={filters.scenario_id} onChange={(event) => updateSearch(setSearchParams, "scenario_id", event.target.value)} placeholder="scn_corridor_001" />
          </FilterField>
          <FilterField label="Template">
            <input value={filters.source_template_id} onChange={(event) => updateSearch(setSearchParams, "source_template_id", event.target.value)} placeholder="blue_delay_center_template" />
          </FilterField>
          <FilterField label="Profile">
            <input value={filters.stochastic_profile_id} onChange={(event) => updateSearch(setSearchParams, "stochastic_profile_id", event.target.value)} placeholder="hybrid_stochastic_v1" />
          </FilterField>
          <FilterField label="Outcome">
            <input value={filters.final_outcome} onChange={(event) => updateSearch(setSearchParams, "final_outcome", event.target.value)} placeholder="blue_success" />
          </FilterField>
          <FilterField label="Quality Band">
            <select value={filters.quality_band} onChange={(event) => updateSearch(setSearchParams, "quality_band", event.target.value)}>
              <option value="">Any</option>
              <option value="strong">Strong</option>
              <option value="good">Good</option>
              <option value="warning">Warning</option>
              <option value="weak">Weak</option>
            </select>
          </FilterField>
          <FilterField label="Seed">
            <input value={filters.seed} onChange={(event) => updateSearch(setSearchParams, "seed", event.target.value)} placeholder="11" />
          </FilterField>
        </div>
      </Panel>

      {query.isLoading ? <LoadingState label="Loading runs" /> : null}
      {query.isError ? <ErrorState title="Run query failed" detail={String(query.error)} /> : null}
      {query.data ? (
        <Panel title="Run Results" subtitle={`${query.data.total} matching runs`}>
          <DataTable
            keyField="run_id"
            rows={query.data.items}
            columns={[
              {
                key: "run_id",
                label: "Run",
                render: (row) => <Link to={`/runs/${row.run_id}`}>{row.run_id}</Link>
              },
              { key: "scenario_id", label: "Scenario" },
              { key: "seed", label: "Seed" },
              {
                key: "final_outcome",
                label: "Outcome",
                render: (row) => <OutcomePill value={row.final_outcome} />
              },
              {
                key: "blue_overall_score",
                label: "Blue",
                render: (row) => toPercent(row.blue_overall_score)
              },
              {
                key: "red_overall_score",
                label: "Red",
                render: (row) => toPercent(row.red_overall_score)
              },
              {
                key: "quality_band",
                label: "Quality",
                render: (row) => <QualityPill value={row.quality_band} />
              },
              { key: "source_blue_coa_template_id", label: "Blue COA Template" }
            ]}
          />
        </Panel>
      ) : null}
    </div>
  );
}

export function RunDetailPage() {
  const { runId } = useParams();
  const [phaseFilter, setPhaseFilter] = useState("");
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);

  const detailQuery = useQuery({
    queryKey: ["run", runId],
    queryFn: () => apiGet<any>(`/runs/${runId}`),
    enabled: Boolean(runId)
  });
  const eventsQuery = useQuery({
    queryKey: ["run-events", runId, phaseFilter],
    queryFn: () =>
      apiGet<ListResponse>(`/runs/${runId}/events${queryString({ phase: phaseFilter || null, limit: 250 })}`),
    enabled: Boolean(runId)
  });

  const events = eventsQuery.data?.items ?? [];
  const phases = Array.from(new Set(events.map((event) => event.phase)));
  const manifest = detailQuery.data?.manifest;
  const finalState = detailQuery.data?.final_state;

  const jumpToEvent = (eventId: string) => {
    setSelectedEventId(eventId);
    const target = document.getElementById(`event-${eventId}`);
    target?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  if (detailQuery.isLoading) {
    return <LoadingState label="Loading run detail" />;
  }

  if (detailQuery.isError || !detailQuery.data) {
    return <ErrorState title="Run detail unavailable" detail={String(detailQuery.error)} />;
  }

  return (
    <div className="page-stack">
      <Panel title={runId ?? "Run"} subtitle="Manifest, outcome, and lineage">
        <KeyValueGrid
          items={[
            { label: "Scenario", value: manifest.scenario_id },
            { label: "Seed", value: manifest.seed },
            { label: "Outcome", value: <OutcomePill value={manifest.final_outcome} /> },
            { label: "Sampling Profile", value: manifest.stochastic_profile_id ?? "--" },
            { label: "Blue COA", value: manifest.blue_coa_id },
            { label: "Red COA", value: manifest.red_coa_id },
            { label: "Blue Template", value: manifest.source_blue_coa_template_id ?? "--" },
            {
              label: "Instantiation",
              value: manifest.instantiation_id ? (
                <Link to={`/instantiations/${manifest.instantiation_id}`}>{manifest.instantiation_id}</Link>
              ) : (
                "--"
              )
            }
          ]}
        />
        <div className="score-grid">
          <ScoreBar label="Blue Overall" value={manifest.summary_scores.blue.overall_score} />
          <ScoreBar label="Red Overall" value={manifest.summary_scores.red.overall_score} />
          <ScoreBar label="Blue Objective Control" value={manifest.summary_scores.blue.objective_control} />
          <ScoreBar label="Red Objective Control" value={manifest.summary_scores.red.objective_control} />
        </div>
      </Panel>

      <div className="split-grid">
        <Panel title="Operational Map" subtitle="Final zone control and scenario geometry">
          <OperationalGraph scenario={detailQuery.data.scenario} finalState={finalState} />
        </Panel>
        <Panel title="Observation Frames" subtitle="Truth state versus side views">
          <div className="observation-grid">
            <ObservationCard side="Blue" truth={finalState?.truth_state} view={finalState?.side_views?.blue} />
            <ObservationCard side="Red" truth={finalState?.truth_state} view={finalState?.side_views?.red} />
          </div>
        </Panel>
      </div>

      <Panel
        title="Timeline and Events"
        subtitle="Turn-by-turn event feed with phase filters"
        actions={
          <div className="inline-control">
            <label htmlFor="phase-filter">Phase</label>
            <select id="phase-filter" value={phaseFilter} onChange={(event) => setPhaseFilter(event.target.value)}>
              <option value="">All</option>
              {phases.map((phase) => (
                <option key={phase} value={phase}>
                  {phase}
                </option>
              ))}
            </select>
          </div>
        }
      >
        {eventsQuery.isLoading ? (
          <LoadingState label="Loading events" />
        ) : (
          <EventTimeline events={events} selectedEventId={selectedEventId} onSelectEvent={setSelectedEventId} />
        )}
      </Panel>

      <div className="split-grid">
        <Panel title="After Action Report" subtitle="Structured run synthesis">
          <div className="report-stack">
            <div>
              <div className="section-label">Mission Outcome</div>
              <OutcomePill value={detailQuery.data.aar?.mission_outcome} />
            </div>
            <CopyList title="Timeline Highlights" items={detailQuery.data.aar?.timeline_highlights ?? []} />
            <CopyList title="Recommended Actions" items={detailQuery.data.aar?.recommended_actions ?? []} />
            <CopyList title="Causal Factors" items={detailQuery.data.aar?.causal_factors ?? []} />
          </div>
        </Panel>
        <Panel title="Lessons Learned" subtitle="Evidence-linked analytical takeaways">
          <div className="lesson-stack">
            {(detailQuery.data.lessons ?? []).map((lesson: any) => (
              <article key={lesson.id} className="lesson-card">
                <div className="lesson-top">
                  <strong>{lesson.observation}</strong>
                  <StatusPill tone="info">{Math.round((lesson.confidence ?? 0) * 100)}% confidence</StatusPill>
                </div>
                <div className="muted-copy">{lesson.implication}</div>
                <div className="tag-list">
                  {(lesson.tags ?? []).map((tag: string) => (
                    <span key={tag} className="reason-chip">
                      {tag}
                    </span>
                  ))}
                </div>
                <EvidenceChips eventIds={lesson.evidence_event_ids ?? []} onJump={jumpToEvent} />
              </article>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}

export function ComparisonsPage() {
  const query = useQuery({
    queryKey: ["comparisons"],
    queryFn: () => apiGet<ListResponse>("/comparisons?limit=50")
  });

  if (query.isLoading) {
    return <LoadingState label="Loading comparisons" />;
  }

  if (query.isError || !query.data) {
    return <ErrorState title="Comparison query failed" detail={String(query.error)} />;
  }

  return (
    <div className="page-stack">
      <Panel title="COA Comparisons" subtitle="Paired-seed recommendations and tradeoffs">
        <DataTable
          keyField="comparison_id"
          rows={query.data.items}
          columns={[
            {
              key: "comparison_id",
              label: "Comparison",
              render: (row) => <Link to={`/comparisons/${row.comparison_id}`}>{row.comparison_id}</Link>
            },
            { key: "scenario_id", label: "Scenario" },
            { key: "recommended_coa", label: "Recommended COA" },
            { key: "sample_count", label: "Samples" },
            {
              key: "confidence",
              label: "Confidence",
              render: (row) => toPercent(row.confidence)
            },
            {
              key: "score_delta",
              label: "Score Delta",
              render: (row) => toPercent(row.score_delta)
            }
          ]}
        />
      </Panel>
    </div>
  );
}

export function ComparisonDetailPage() {
  const { comparisonId } = useParams();
  const query = useQuery({
    queryKey: ["comparison", comparisonId],
    queryFn: () => apiGet<any>(`/comparisons/${comparisonId}`),
    enabled: Boolean(comparisonId)
  });

  if (query.isLoading) {
    return <LoadingState label="Loading comparison detail" />;
  }

  if (query.isError || !query.data) {
    return <ErrorState title="Comparison detail unavailable" detail={String(query.error)} />;
  }

  const comparison = query.data.comparison;
  const metricRows = query.data.metric_rows ?? [];
  const linkedRuns = query.data.linked_runs ?? [];

  return (
    <div className="page-stack">
      <Panel
        title={comparison.id}
        subtitle={`Scenario ${comparison.scenario_id}`}
        actions={<StatusPill tone="good">{comparison.recommended_coa}</StatusPill>}
      >
        <div className="hero-metrics">
          <MetricCard label="Confidence" value={toPercent(comparison.paired_seed_stats?.confidence)} note="Recommendation stability" />
          <MetricCard label="Score Delta" value={toPercent(comparison.paired_seed_stats?.score_delta)} note="Mean overall score gap" />
          <MetricCard label="Casualty Delta" value={toPercent(comparison.paired_seed_stats?.casualty_delta)} note="Lower is better for the recommended option" />
          <MetricCard label="Samples" value={comparison.sample_count} note={`Seeds: ${(comparison.seed_list ?? []).join(", ")}`} />
        </div>
        <div className="comparison-tradeoff">{comparison.tradeoffs}</div>
      </Panel>

      <Panel title="Per-COA Metrics" subtitle="Mean results across the paired seed set">
        <div className="comparison-card-grid">
          {metricRows.map((row: any) => (
            <article key={row.coa_id} className="comparison-metric-card">
              <div className="comparison-card-top">
                <strong>{row.coa_id}</strong>
                <StatusPill tone={row.coa_id === comparison.recommended_coa ? "good" : "neutral"}>
                  {row.coa_id === comparison.recommended_coa ? "Recommended" : "Alternative"}
                </StatusPill>
              </div>
              <ScoreBar label="Overall Score" value={row.mean_overall_score ?? 0} />
              <ScoreBar label="Objective Control" value={row.mean_objective_control ?? 0} />
              <ScoreBar label="Force Preservation" value={row.mean_force_preservation ?? 0} />
              <ScoreBar label="Sustainment" value={row.mean_sustainment ?? 0} />
              <ScoreBar label="Tempo" value={row.mean_tempo ?? 0} />
            </article>
          ))}
        </div>
      </Panel>

      <Panel title="Linked Runs" subtitle="Individual realizations behind this recommendation">
        <DataTable
          keyField="run_id"
          rows={linkedRuns}
          columns={[
            {
              key: "run_id",
              label: "Run",
              render: (row) => <Link to={`/runs/${row.run_id}`}>{row.run_id}</Link>
            },
            { key: "seed", label: "Seed" },
            { key: "blue_actor_id", label: "Blue Actor" },
            {
              key: "final_outcome",
              label: "Outcome",
              render: (row) => <OutcomePill value={row.final_outcome} />
            },
            {
              key: "quality_band",
              label: "Quality",
              render: (row) => <QualityPill value={row.quality_band} />
            }
          ]}
        />
      </Panel>
    </div>
  );
}

export function InstantiationDetailPage() {
  const { instantiationId } = useParams();
  const query = useQuery({
    queryKey: ["instantiation", instantiationId],
    queryFn: () => apiGet<any>(`/instantiations/${instantiationId}`),
    enabled: Boolean(instantiationId)
  });

  if (query.isLoading) {
    return <LoadingState label="Loading instantiation detail" />;
  }

  if (query.isError || !query.data) {
    return <ErrorState title="Instantiation detail unavailable" detail={String(query.error)} />;
  }

  return (
    <div className="page-stack">
      <Panel title={instantiationId ?? "Instantiation"} subtitle="Realized assets sampled from parameterized templates">
        <KeyValueGrid
          items={[
            { label: "Sampling Profile", value: query.data.instantiation.stochastic_profile_id },
            { label: "Seed", value: query.data.instantiation.seed },
            { label: "Scenario", value: query.data.scenario.name },
            { label: "Blue COA", value: query.data.blue_coa.name ?? query.data.blue_coa.id },
            { label: "Red COA", value: query.data.red_coa.name ?? query.data.red_coa.id }
          ]}
        />
      </Panel>
      <div className="split-grid">
        <Panel title="Realized Scenario" subtitle="Scenario geometry and sampled environment">
          <OperationalGraph scenario={query.data.scenario} />
          <div className="tag-list">
            <span className="reason-chip">Weather: {query.data.scenario.environment?.weather}</span>
            <span className="reason-chip">Visibility: {query.data.scenario.environment?.visibility}</span>
          </div>
        </Panel>
        <Panel title="Sampled Values" subtitle="Stochastic realization audit trail">
          <pre className="json-panel">{JSON.stringify(query.data.instantiation.sampled_values, null, 2)}</pre>
        </Panel>
      </div>
    </div>
  );
}

export function ActionsPage() {
  const navigate = useNavigate();
  const templatesQuery = useQuery({
    queryKey: ["approved-templates"],
    queryFn: () => apiGet<ListResponse>("/templates?approval_state=approved_for_batch&limit=200")
  });

  const templateBuckets = useMemo(() => {
    const items = templatesQuery.data?.items ?? [];
    return {
      scenario: items.filter((item) => item.template_kind === "scenario_template"),
      blueForce: items.filter((item) => item.template_kind === "force_template" && item.side === "blue"),
      redForce: items.filter((item) => item.template_kind === "force_template" && item.side === "red"),
      blueCoa: items.filter((item) => item.template_kind === "coa_template" && item.side === "blue"),
      redCoa: items.filter((item) => item.template_kind === "coa_template" && item.side === "red")
    };
  }, [templatesQuery.data]);

  const [scenarioTemplateId, setScenarioTemplateId] = useState("");
  const [blueForceTemplateId, setBlueForceTemplateId] = useState("");
  const [redForceTemplateId, setRedForceTemplateId] = useState("");
  const [blueCoaTemplateId, setBlueCoaTemplateId] = useState("");
  const [blueBatchCoaIds, setBlueBatchCoaIds] = useState<string[]>([]);
  const [redCoaTemplateId, setRedCoaTemplateId] = useState("");
  const [seed, setSeed] = useState("42");
  const [batchSeeds, setBatchSeeds] = useState("11,22,33");
  const [samplingProfile, setSamplingProfile] = useState("hybrid_stochastic_v1");
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [redirectedJobId, setRedirectedJobId] = useState<string | null>(null);

  useEffect(() => {
    if (!templatesQuery.data) {
      return;
    }
    if (!scenarioTemplateId && templateBuckets.scenario[0]) {
      setScenarioTemplateId(templateBuckets.scenario[0].template_id);
    }
    if (!blueForceTemplateId && templateBuckets.blueForce[0]) {
      setBlueForceTemplateId(templateBuckets.blueForce[0].template_id);
    }
    if (!redForceTemplateId && templateBuckets.redForce[0]) {
      setRedForceTemplateId(templateBuckets.redForce[0].template_id);
    }
    if (!blueCoaTemplateId && templateBuckets.blueCoa[0]) {
      setBlueCoaTemplateId(templateBuckets.blueCoa[0].template_id);
    }
    if (!redCoaTemplateId && templateBuckets.redCoa[0]) {
      setRedCoaTemplateId(templateBuckets.redCoa[0].template_id);
    }
    if (!blueBatchCoaIds.length && templateBuckets.blueCoa.length) {
      setBlueBatchCoaIds(templateBuckets.blueCoa.slice(0, 2).map((item) => item.template_id));
    }
  }, [
    templatesQuery.data,
    templateBuckets,
    scenarioTemplateId,
    blueForceTemplateId,
    redForceTemplateId,
    blueCoaTemplateId,
    redCoaTemplateId,
    blueBatchCoaIds
  ]);

  const instantiateMutation = useMutation({
    mutationFn: () =>
      apiPost<{ job_id: string }>("/actions/instantiate", {
        scenario_template_id: scenarioTemplateId,
        blue_force_template_id: blueForceTemplateId,
        red_force_template_id: redForceTemplateId,
        blue_coa_template_id: blueCoaTemplateId,
        red_coa_template_id: redCoaTemplateId,
        seed: Number(seed),
        sampling_profile: samplingProfile
      }),
    onSuccess: (payload) => setActiveJobId(payload.job_id)
  });

  const batchMutation = useMutation({
    mutationFn: () =>
      apiPost<{ job_id: string }>("/actions/run-batch", {
        scenario_template_id: scenarioTemplateId,
        blue_force_template_id: blueForceTemplateId,
        red_force_template_id: redForceTemplateId,
        blue_coa_template_ids: blueBatchCoaIds,
        red_coa_template_id: redCoaTemplateId,
        seeds: parseSeeds(batchSeeds),
        sampling_profile: samplingProfile,
        require_approved: true
      }),
    onSuccess: (payload) => setActiveJobId(payload.job_id)
  });

  const jobQuery = useQuery({
    queryKey: ["job", activeJobId],
    queryFn: () => apiGet<JobStatus>(`/actions/jobs/${activeJobId}`),
    enabled: Boolean(activeJobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 1000 : false;
    }
  });

  useEffect(() => {
    if (!jobQuery.data || jobQuery.data.status !== "succeeded" || redirectedJobId === jobQuery.data.id) {
      return;
    }
    if (jobQuery.data.result?.comparison_id) {
      setRedirectedJobId(jobQuery.data.id);
      navigate(`/comparisons/${jobQuery.data.result.comparison_id}`);
      return;
    }
    if (jobQuery.data.result?.instantiation_id) {
      setRedirectedJobId(jobQuery.data.id);
      navigate(`/instantiations/${jobQuery.data.result.instantiation_id}`);
    }
  }, [jobQuery.data, navigate, redirectedJobId]);

  return (
    <div className="page-stack">
      <Panel title="Controlled Actions" subtitle="Launch bounded workflows against approved templates">
        <div className="action-layout">
          <div className="action-form-stack">
            <ActionFormSection title="Instantiate Assets" description="Materialize one realized scenario/force/COA bundle from approved templates.">
              <TemplateSelectors
                templateBuckets={templateBuckets}
                scenarioTemplateId={scenarioTemplateId}
                setScenarioTemplateId={setScenarioTemplateId}
                blueForceTemplateId={blueForceTemplateId}
                setBlueForceTemplateId={setBlueForceTemplateId}
                redForceTemplateId={redForceTemplateId}
                setRedForceTemplateId={setRedForceTemplateId}
                redCoaTemplateId={redCoaTemplateId}
                setRedCoaTemplateId={setRedCoaTemplateId}
              />
              <FilterField label="Blue COA Template">
                <select value={blueCoaTemplateId} onChange={(event) => setBlueCoaTemplateId(event.target.value)}>
                  {templateBuckets.blueCoa.map((item) => (
                    <option key={item.template_id} value={item.template_id}>
                      {item.template_id}
                    </option>
                  ))}
                </select>
              </FilterField>
              <div className="inline-form-row">
                <FilterField label="Seed">
                  <input value={seed} onChange={(event) => setSeed(event.target.value)} />
                </FilterField>
                <FilterField label="Sampling Profile">
                  <input value={samplingProfile} onChange={(event) => setSamplingProfile(event.target.value)} />
                </FilterField>
              </div>
              <button className="action-button" onClick={() => instantiateMutation.mutate()} disabled={instantiateMutation.isPending || !scenarioTemplateId}>
                Instantiate Approved Bundle
              </button>
            </ActionFormSection>

            <ActionFormSection title="Run Approved Batch" description="Launch a paired-seed comparison across multiple blue COA templates.">
              <TemplateSelectors
                templateBuckets={templateBuckets}
                scenarioTemplateId={scenarioTemplateId}
                setScenarioTemplateId={setScenarioTemplateId}
                blueForceTemplateId={blueForceTemplateId}
                setBlueForceTemplateId={setBlueForceTemplateId}
                redForceTemplateId={redForceTemplateId}
                setRedForceTemplateId={setRedForceTemplateId}
                redCoaTemplateId={redCoaTemplateId}
                setRedCoaTemplateId={setRedCoaTemplateId}
              />
              <FilterField label="Blue COA Templates">
                <div className="checkbox-list">
                  {templateBuckets.blueCoa.map((item) => (
                    <label key={item.template_id} className="checkbox-item">
                      <input
                        type="checkbox"
                        checked={blueBatchCoaIds.includes(item.template_id)}
                        onChange={() => toggleSelection(item.template_id, blueBatchCoaIds, setBlueBatchCoaIds)}
                      />
                      <span>{item.template_id}</span>
                    </label>
                  ))}
                </div>
              </FilterField>
              <div className="inline-form-row">
                <FilterField label="Seeds">
                  <input value={batchSeeds} onChange={(event) => setBatchSeeds(event.target.value)} placeholder="11,22,33" />
                </FilterField>
                <FilterField label="Sampling Profile">
                  <input value={samplingProfile} onChange={(event) => setSamplingProfile(event.target.value)} />
                </FilterField>
              </div>
              <button className="action-button" onClick={() => batchMutation.mutate()} disabled={batchMutation.isPending || blueBatchCoaIds.length < 1}>
                Run Approved Batch
              </button>
            </ActionFormSection>
          </div>

          <Panel title="Job Status" subtitle="Polling-based workflow tracking">
            {jobQuery.isLoading ? <LoadingState label="Polling job" /> : null}
            {jobQuery.data ? (
              <div className="job-card">
                <div className="job-card-top">
                  <strong>{jobQuery.data.id}</strong>
                  <StatusPill tone={jobTone(jobQuery.data.status)}>{jobQuery.data.status}</StatusPill>
                </div>
                {jobQuery.data.result ? <pre className="json-panel">{JSON.stringify(jobQuery.data.result, null, 2)}</pre> : null}
                {jobQuery.data.error ? <ErrorState title="Job failed" detail={jobQuery.data.error} /> : null}
              </div>
            ) : (
              <EmptyState title="No active job" detail="Submit an instantiation or approved batch run to track it here." />
            )}
          </Panel>
        </div>
      </Panel>
    </div>
  );
}

function ActionFormSection({
  title,
  description,
  children
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section className="action-form-section">
      <div className="section-label">{title}</div>
      <div className="muted-copy">{description}</div>
      <div className="action-form-body">{children}</div>
    </section>
  );
}

function TemplateSelectors({
  templateBuckets,
  scenarioTemplateId,
  setScenarioTemplateId,
  blueForceTemplateId,
  setBlueForceTemplateId,
  redForceTemplateId,
  setRedForceTemplateId,
  redCoaTemplateId,
  setRedCoaTemplateId
}: {
  templateBuckets: Record<string, any[]>;
  scenarioTemplateId: string;
  setScenarioTemplateId: (value: string) => void;
  blueForceTemplateId: string;
  setBlueForceTemplateId: (value: string) => void;
  redForceTemplateId: string;
  setRedForceTemplateId: (value: string) => void;
  redCoaTemplateId: string;
  setRedCoaTemplateId: (value: string) => void;
}) {
  return (
    <>
      <FilterField label="Scenario Template">
        <select value={scenarioTemplateId} onChange={(event) => setScenarioTemplateId(event.target.value)}>
          {templateBuckets.scenario.map((item) => (
            <option key={item.template_id} value={item.template_id}>
              {item.template_id}
            </option>
          ))}
        </select>
      </FilterField>
      <div className="inline-form-row">
        <FilterField label="Blue Force Template">
          <select value={blueForceTemplateId} onChange={(event) => setBlueForceTemplateId(event.target.value)}>
            {templateBuckets.blueForce.map((item) => (
              <option key={item.template_id} value={item.template_id}>
                {item.template_id}
              </option>
            ))}
          </select>
        </FilterField>
        <FilterField label="Red Force Template">
          <select value={redForceTemplateId} onChange={(event) => setRedForceTemplateId(event.target.value)}>
            {templateBuckets.redForce.map((item) => (
              <option key={item.template_id} value={item.template_id}>
                {item.template_id}
              </option>
            ))}
          </select>
        </FilterField>
      </div>
      <FilterField label="Red COA Template">
        <select value={redCoaTemplateId} onChange={(event) => setRedCoaTemplateId(event.target.value)}>
          {templateBuckets.redCoa.map((item) => (
            <option key={item.template_id} value={item.template_id}>
              {item.template_id}
            </option>
          ))}
        </select>
      </FilterField>
    </>
  );
}

function ObservationCard({
  side,
  truth,
  view
}: {
  side: string;
  truth?: any;
  view?: any;
}) {
  return (
    <article className="observation-card">
      <div className="section-label">{side} observation frame</div>
      <KeyValueGrid
        items={[
          { label: "Intel Confidence", value: toPercent(view?.intel_confidence) },
          { label: "Known Contacts", value: Object.keys(view?.known_enemy_positions ?? {}).length },
          { label: "Suspected Zones", value: (view?.suspected_enemy_zones ?? []).join(", ") || "--" },
          { label: "False Contacts", value: (view?.false_contact_zones ?? []).join(", ") || "--" },
          { label: "Truth Zones", value: Object.keys(truth?.zone_control ?? {}).length }
        ]}
      />
    </article>
  );
}

function CopyList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="copy-list">
      <div className="section-label">{title}</div>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function FilterField({
  label,
  children
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="filter-field">
      <span>{label}</span>
      {children}
    </label>
  );
}

function updateSearch(
  setSearchParams: (nextInit: URLSearchParams) => void,
  key: string,
  value: string
) {
  const next = new URLSearchParams(window.location.search);
  if (!value) {
    next.delete(key);
  } else {
    next.set(key, value);
  }
  setSearchParams(next);
}

function toPercent(value: number | null | undefined) {
  return `${Math.round((value ?? 0) * 100)}%`;
}

function describeTemplateVariability(template: any, kind: string): string[] {
  if (kind === "scenario_template") {
    return [
      `${(template.weather_options ?? []).length} weather options`,
      `${(template.visibility_options ?? []).length} visibility states`,
      `${Object.keys(template.zone_strategic_value_adjustments ?? {}).length} zone value ranges`
    ];
  }
  if (kind === "force_template") {
    return [
      `${(template.unit_variability ?? []).length} unit variability rows`,
      `${template.doctrine ?? "no"} doctrine profile`,
      `${(template.reinforcement_options ?? []).length} reinforcement options`
    ].filter(Boolean);
  }
  return [
    `${(template.action_variations ?? []).length} branch points`,
    `${(template.strategy_tags ?? []).join(", ") || "no strategy tags"}`,
    `${template.side ?? "unknown"} side orientation`
  ];
}

function parseSeeds(value: string) {
  return value
    .split(",")
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isFinite(item));
}

function toggleSelection(value: string, selected: string[], setSelected: (value: string[]) => void) {
  if (selected.includes(value)) {
    setSelected(selected.filter((item) => item !== value));
    return;
  }
  setSelected([...selected, value]);
}

function jobTone(status: string) {
  if (status === "succeeded") return "good";
  if (status === "failed") return "warning";
  if (status === "running") return "info";
  return "neutral";
}
