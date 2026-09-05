import { Navigate, Route, Routes, useParams } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { ConversationPage } from "./pages/ConversationPage";
import { ConversationsPage } from "./pages/ConversationsPage";
import { NewConversationPage } from "./pages/NewConversationPage";
import { ProjectPage } from "./pages/ProjectPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { WorkflowPage } from "./pages/WorkflowPage";
import { WorkflowsPage } from "./pages/WorkflowsPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate replace to="/projects" />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="projects/:projectId" element={<ProjectPage />} />
        <Route
          path="projects/:projectId/workflows/:workflowId"
          element={<LegacyWorkflowRedirect />}
        />
        <Route path="workflows" element={<WorkflowsPage />} />
        <Route path="workflows/:workflowId" element={<WorkflowPage />} />
        <Route path="conversations" element={<ConversationsPage />} />
        <Route path="conversations/new" element={<NewConversationPage />} />
        <Route path="conversations/:conversationId" element={<ConversationPage />} />
        <Route
          path="conversations/:conversationId/branches/:branchId"
          element={<ConversationPage />}
        />
        <Route path="*" element={<Navigate replace to="/projects" />} />
      </Route>
    </Routes>
  );
}

function LegacyWorkflowRedirect() {
  const { workflowId } = useParams();
  return <Navigate replace to={workflowId ? `/workflows/${workflowId}` : "/workflows"} />;
}
