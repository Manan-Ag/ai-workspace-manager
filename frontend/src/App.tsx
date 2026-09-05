import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useParams } from "react-router-dom";

import { api } from "./api/client";
import { AppShell } from "./components/AppShell";
import { ConversationPage } from "./pages/ConversationPage";
import { ConversationsPage } from "./pages/ConversationsPage";
import { NewConversationPage } from "./pages/NewConversationPage";
import { ProjectPage } from "./pages/ProjectPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { WorkflowPage } from "./pages/WorkflowPage";
import { WorkflowsPage } from "./pages/WorkflowsPage";

export default function App() {
  const [sessionState, setSessionState] = useState<"checking" | "guest" | "active">(
    "checking",
  );
  const [sessionError, setSessionError] = useState("");
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    api
      .getGuestSession()
      .then(({ active }) => setSessionState(active ? "active" : "guest"))
      .catch(() => setSessionState("guest"));
  }, []);

  async function startGuestWorkspace() {
    setStarting(true);
    setSessionError("");
    try {
      await api.createGuestSession();
      setSessionState("active");
    } catch (error) {
      setSessionError(
        error instanceof Error ? error.message : "Could not start the guest workspace.",
      );
    } finally {
      setStarting(false);
    }
  }

  if (sessionState === "checking") {
    return (
      <main className="guest-gate guest-gate-loading" aria-label="Loading workspace">
        <span className="guest-loader" />
      </main>
    );
  }

  if (sessionState === "guest") {
    return (
      <main className="guest-gate">
        <section className="guest-card">
          <div className="guest-brand-mark">W</div>
          <p className="eyebrow accent">AI Workspace</p>
          <h1>Explore ideas without losing the thread.</h1>
          <p className="guest-lede">
            Chat with Gemini, branch any answer into a focused path, and reuse
            workflows across projects. Your guest workspace is private to this
            browser.
          </p>
          <div className="guest-feature-row" aria-label="Product highlights">
            <span>Branching conversations</span>
            <span>Reusable workflows</span>
            <span>Private guest space</span>
          </div>
          {sessionError && <div className="error-banner">{sessionError}</div>}
          <button
            className="primary-button guest-start-button"
            disabled={starting}
            onClick={startGuestWorkspace}
          >
            {starting ? "Opening your workspace…" : "Continue as guest"}
          </button>
          <small className="guest-note">
            No account needed. This workspace stays with this browser for 30 days.
          </small>
        </section>
      </main>
    );
  }

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
