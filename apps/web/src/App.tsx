import { Navigate, Route, Routes } from "react-router-dom";

import { ShellLayout } from "./components";
import {
  ActionsPage,
  ComparisonDetailPage,
  ComparisonsPage,
  InstantiationDetailPage,
  OverviewPage,
  RunDetailPage,
  RunsPage,
  TemplateDetailPage,
  TemplatesPage
} from "./pages";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<ShellLayout />}>
        <Route index element={<OverviewPage />} />
        <Route path="templates" element={<TemplatesPage />} />
        <Route path="templates/:templateId" element={<TemplateDetailPage />} />
        <Route path="runs" element={<RunsPage />} />
        <Route path="runs/:runId" element={<RunDetailPage />} />
        <Route path="comparisons" element={<ComparisonsPage />} />
        <Route path="comparisons/:comparisonId" element={<ComparisonDetailPage />} />
        <Route path="instantiations/:instantiationId" element={<InstantiationDetailPage />} />
        <Route path="actions" element={<ActionsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
