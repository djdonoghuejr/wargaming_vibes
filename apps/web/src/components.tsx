import type { ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { apiGet } from "./api";

export function ShellLayout() {
  const summaryQuery = useQuery({
    queryKey: ["catalog-summary"],
    queryFn: () => apiGet<any>("/catalog/summary")
  });

  const counts = summaryQuery.data?.counts ?? {};

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="sidebar-kicker">Operational Experiment Generator</div>
          <div className="sidebar-title">Analyst Console</div>
        </div>
        <nav className="sidebar-nav">
          <NavItem to="/">Overview</NavItem>
          <NavItem to="/templates">Templates</NavItem>
          <NavItem to="/runs">Runs</NavItem>
          <NavItem to="/comparisons">Comparisons</NavItem>
          <NavItem to="/actions">Actions</NavItem>
        </nav>
        <div className="sidebar-footnote">
          <div>Catalog-backed analyst workspace</div>
          <div className="sidebar-footnote-muted">Map-first, seed-replayable, evidence-linked.</div>
        </div>
      </aside>
      <main className="main-stage">
        <header className="topbar">
          <div>
            <div className="eyebrow">Operational Analyst Workspace</div>
            <h1>Structured experimentation, comparison, and evidence review.</h1>
          </div>
          <div className="topbar-status">
            <StatusPill tone={summaryQuery.isError ? "warning" : "good"}>
              {summaryQuery.isError ? "Catalog unavailable" : "Catalog online"}
            </StatusPill>
          </div>
        </header>
        <div className="workspace-grid">
          <section className="workspace-main">
            <Outlet />
          </section>
          <aside className="workspace-context">
            <Panel title="Catalog Posture" subtitle="Current query surface">
              <div className="context-metrics">
                <MetricMini label="Templates" value={counts.templates ?? "--"} />
                <MetricMini label="Approved" value={counts.approved_templates ?? "--"} />
                <MetricMini label="Runs" value={counts.runs ?? "--"} />
                <MetricMini label="Comparisons" value={counts.comparisons ?? "--"} />
              </div>
            </Panel>
            <Panel title="Recent Signal" subtitle="Latest analytical movement">
              {summaryQuery.isLoading ? (
                <LoadingState label="Loading catalog summary" />
              ) : summaryQuery.isError ? (
                <ErrorState title="Catalog unavailable" detail={String(summaryQuery.error)} />
              ) : (
                <div className="context-list">
                  {(summaryQuery.data?.recent_runs ?? []).slice(0, 3).map((run: any) => (
                    <div key={run.run_id} className="context-list-item">
                      <div className="context-list-title">{run.run_id}</div>
                      <OutcomePill value={run.final_outcome} />
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          </aside>
        </div>
      </main>
    </div>
  );
}

function NavItem({ to, children }: { to: string; children: ReactNode }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) => (isActive ? "nav-item nav-item-active" : "nav-item")}
      end={to === "/"}
    >
      {children}
    </NavLink>
  );
}

export function Panel({
  title,
  subtitle,
  actions,
  children
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2>{title}</h2>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        {actions ? <div className="panel-actions">{actions}</div> : null}
      </div>
      <div className="panel-body">{children}</div>
    </section>
  );
}

export function MetricCard({
  label,
  value,
  note
}: {
  label: string;
  value: string | number;
  note?: string;
}) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {note ? <div className="metric-note">{note}</div> : null}
    </div>
  );
}

export function MetricMini({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="metric-mini">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function StatusPill({
  tone,
  children
}: {
  tone: "good" | "warning" | "neutral" | "info";
  children: ReactNode;
}) {
  return <span className={`pill pill-${tone}`}>{children}</span>;
}

export function ApprovalPill({ value }: { value?: string }) {
  const tone =
    value === "approved_for_batch"
      ? "good"
      : value === "promoted"
        ? "info"
        : value === "quarantined"
          ? "warning"
          : "neutral";
  return <StatusPill tone={tone}>{value ?? "unknown"}</StatusPill>;
}

export function OutcomePill({ value }: { value?: string }) {
  const tone = value?.startsWith("blue")
    ? "good"
    : value?.startsWith("red")
      ? "warning"
      : value?.includes("success")
        ? "good"
        : value?.includes("repulsed")
          ? "info"
          : "neutral";
  return <StatusPill tone={tone}>{value ?? "unknown"}</StatusPill>;
}

export function QualityPill({ value }: { value?: string }) {
  const tone =
    value === "strong" || value === "good"
      ? "good"
      : value === "warning"
        ? "info"
        : "warning";
  return <StatusPill tone={tone}>{value ?? "unknown"}</StatusPill>;
}

export function LoadingState({ label }: { label: string }) {
  return <div className="loading-state">{label}...</div>;
}

export function EmptyState({
  title,
  detail
}: {
  title: string;
  detail?: string;
}) {
  return (
    <div className="empty-state">
      <div className="empty-title">{title}</div>
      {detail ? <div className="empty-detail">{detail}</div> : null}
    </div>
  );
}

export function ErrorState({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="error-state">
      <div className="error-title">{title}</div>
      {detail ? <div className="error-detail">{detail}</div> : null}
    </div>
  );
}

export function KeyValueGrid({ items }: { items: Array<{ label: string; value: ReactNode }> }) {
  return (
    <dl className="key-value-grid">
      {items.map((item) => (
        <div key={item.label} className="key-value-row">
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function DataTable({
  columns,
  rows,
  keyField
}: {
  columns: Array<{ key: string; label: string; render?: (row: any) => ReactNode }>;
  rows: any[];
  keyField: string;
}) {
  if (!rows.length) {
    return <EmptyState title="No rows found" detail="Adjust filters or select a different analytical slice." />;
  }

  return (
    <div className="table-shell">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key}>{column.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row[keyField]}>
              {columns.map((column) => (
                <td key={column.key}>{column.render ? column.render(row) : String(row[column.key] ?? "--")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ScoreBar({ label, value }: { label: string; value: number }) {
  const percentage = Math.max(0, Math.min(100, Math.round((value ?? 0) * 100)));
  return (
    <div className="score-bar">
      <div className="score-bar-meta">
        <span>{label}</span>
        <strong>{percentage}%</strong>
      </div>
      <div className="score-bar-track">
        <div className="score-bar-fill" style={{ width: `${percentage}%` }} />
      </div>
    </div>
  );
}

export function OperationalGraph({
  scenario,
  finalState
}: {
  scenario?: any;
  finalState?: any;
}) {
  if (!scenario) {
    return <LoadingState label="Scenario geometry unavailable" />;
  }

  const zones = scenario.zones ?? [];
  const layout = computeZoneLayout(zones);
  const control = finalState?.truth_state?.zone_control ?? scenario.initial_zone_control ?? {};

  return (
    <div className="graph-shell">
      <svg viewBox="0 0 760 420" className="graph-svg" role="img" aria-label="Operational map">
        <defs>
          <pattern id="map-grid" width="24" height="24" patternUnits="userSpaceOnUse">
            <path d="M 24 0 L 0 0 0 24" fill="none" stroke="rgba(70,92,98,0.08)" strokeWidth="1" />
          </pattern>
        </defs>
        <rect x="0" y="0" width="760" height="420" fill="url(#map-grid)" rx="18" />
        {(scenario.edges ?? []).map((edge: any, index: number) => {
          const a = layout[edge.a];
          const b = layout[edge.b];
          if (!a || !b) {
            return null;
          }
          return (
            <line
              key={`${edge.a}-${edge.b}-${index}`}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke="rgba(76, 97, 110, 0.38)"
              strokeWidth="6"
            />
          );
        })}
        {zones.map((zone: any) => {
          const point = layout[zone.id];
          const tone = zoneTone(control[zone.id]);
          return (
            <g key={zone.id} transform={`translate(${point.x}, ${point.y})`}>
              <circle r="42" className={`zone-node zone-${tone}`} />
              <text className="zone-node-id" textAnchor="middle" y="-2">
                {zone.id}
              </text>
              <text className="zone-node-name" textAnchor="middle" y="18">
                {zone.name}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="graph-legend">
        <StatusPill tone="good">Blue control</StatusPill>
        <StatusPill tone="warning">Red control</StatusPill>
        <StatusPill tone="info">Contested</StatusPill>
        <StatusPill tone="neutral">Neutral</StatusPill>
      </div>
    </div>
  );
}

export function EventTimeline({
  events,
  selectedEventId,
  onSelectEvent
}: {
  events: any[];
  selectedEventId?: string | null;
  onSelectEvent?: (eventId: string) => void;
}) {
  const grouped = new Map<number, Record<string, number>>();
  events.forEach((event) => {
    const byPhase = grouped.get(event.turn) ?? {};
    byPhase[event.phase] = (byPhase[event.phase] ?? 0) + 1;
    grouped.set(event.turn, byPhase);
  });
  const turns = Array.from(grouped.entries()).sort((a, b) => a[0] - b[0]);

  return (
    <div className="timeline-shell">
      <div className="timeline-band">
        {turns.map(([turn, phases]) => (
          <div key={turn} className="timeline-turn">
            <div className="timeline-turn-label">Turn {turn}</div>
            <div className="timeline-phase-stack">
              {Object.entries(phases).map(([phase, count]) => (
                <div key={phase} className="timeline-phase-chip">
                  <span>{phase}</span>
                  <strong>{count}</strong>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="event-feed">
        {events.map((event) => (
          <button
            type="button"
            key={event.id}
            id={`event-${event.id}`}
            className={event.id === selectedEventId ? "event-row event-row-selected" : "event-row"}
            onClick={() => onSelectEvent?.(event.id)}
          >
            <div className="event-row-top">
              <span>Turn {event.turn}</span>
              <span>{event.phase}</span>
              <OutcomePill value={event.adjudication?.combat_result} />
            </div>
            <div className="event-row-main">
              <strong>{event.action_type}</strong>
              <span>{event.target_zone ?? "no target"}</span>
              <span>{event.actor_side}</span>
            </div>
            <div className="event-row-reasons">
              {(event.adjudication?.reason_codes ?? []).map((reason: string) => (
                <span key={reason} className="reason-chip">
                  {reason}
                </span>
              ))}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

export function EvidenceChips({
  eventIds,
  onJump
}: {
  eventIds: string[];
  onJump: (eventId: string) => void;
}) {
  return (
    <div className="evidence-chip-row">
      {eventIds.map((eventId) => (
        <button key={eventId} type="button" className="evidence-chip" onClick={() => onJump(eventId)}>
          {eventId}
        </button>
      ))}
    </div>
  );
}

function computeZoneLayout(zones: any[]) {
  const layout: Record<string, { x: number; y: number }> = {};
  const cols = Math.max(2, Math.ceil(Math.sqrt(zones.length)));
  zones.forEach((zone, index) => {
    const row = Math.floor(index / cols);
    const col = index % cols;
    layout[zone.id] = {
      x: 110 + col * 190 + (row % 2 ? 44 : 0),
      y: 96 + row * 156
    };
  });
  return layout;
}

function zoneTone(controlState?: string) {
  if (controlState === "blue") return "blue";
  if (controlState === "red") return "red";
  if (controlState === "contested") return "contested";
  return "neutral";
}
