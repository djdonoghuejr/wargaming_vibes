import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";

const summaryPayload = {
  catalog_path: "C:/catalog.duckdb",
  counts: {
    templates: 5,
    approved_templates: 5,
    runs: 12,
    comparisons: 3,
    lessons: 22,
    aars: 12
  },
  recent_runs: [
    {
      run_id: "run_alpha",
      scenario_id: "scn_corridor_001",
      final_outcome: "blue_success",
      blue_overall_score: 0.71,
      red_overall_score: 0.53,
      quality_band: "strong"
    }
  ],
  recent_comparisons: [
    {
      comparison_id: "comparison_alpha",
      scenario_id: "scn_corridor_001",
      recommended_coa: "blue_delay_center",
      confidence: 0.61,
      sample_count: 3
    }
  ],
  recent_templates: [
    {
      template_id: "blue_delay_center_template",
      template_kind: "coa_template",
      approval_state: "approved_for_batch",
      quality_score: 1
    }
  ]
};

function renderApp(initialEntry: string, handlers: Record<string, any>) {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false
      }
    }
  });

  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const path = url.replace("http://127.0.0.1:8000", "");
    const payload = handlers[path];
    if (!payload) {
      return new Response(JSON.stringify({ detail: `No mock for ${path}` }), {
        status: 404,
        headers: { "Content-Type": "application/json" }
      });
    }
    return new Response(JSON.stringify(payload), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    });
  });

  vi.stubGlobal("fetch", fetchMock);
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[initialEntry]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <App />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("analyst console", () => {
  it("renders the overview workspace", async () => {
    renderApp("/", {
      "/catalog/summary": summaryPayload
    });

    expect(await screen.findByText("Analyst Console")).toBeInTheDocument();
    expect(await screen.findByText("Recent Comparisons")).toBeInTheDocument();
    expect(await screen.findByText("comparison_alpha")).toBeInTheDocument();
    expect((await screen.findAllByText("run_alpha")).length).toBeGreaterThan(0);
  });

  it("renders the templates explorer with server data", async () => {
    renderApp("/templates", {
      "/catalog/summary": summaryPayload,
      "/templates?approval_state=approved_for_batch&limit=50": {
        total: 1,
        limit: 50,
        offset: 0,
        items: [
          {
            template_id: "blue_delay_center_template",
            template_kind: "coa_template",
            side: "blue",
            doctrine: null,
            base_asset_id: "blue_delay_center",
            approval_state: "approved_for_batch",
            quality_band: "strong",
            warning_count: 0
          }
        ]
      }
    });

    expect(await screen.findByText("Templates Explorer")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("blue_delay_center_template")).toBeInTheDocument();
    });
  });
});
