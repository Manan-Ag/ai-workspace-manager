import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import type { Project, Workflow } from "../types";

export function NewConversationPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [projects, setProjects] = useState<Project[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [projectWorkflows, setProjectWorkflows] = useState<Workflow[]>([]);
  const [title, setTitle] = useState("");
  const [projectId, setProjectId] = useState(searchParams.get("project") ?? "");
  const [workflowIds, setWorkflowIds] = useState<string[]>([]);
  const [inheritProjectWorkflows, setInheritProjectWorkflows] = useState(true);
  const [modelName, setModelName] = useState("");
  const [temperature, setTemperature] = useState(0.7);
  const [modelSettingsEdited, setModelSettingsEdited] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.listProjects(), api.listWorkflows()])
      .then(([projectItems, workflowItems]) => {
        setProjects(projectItems);
        setWorkflows(workflowItems);
        const requestedWorkflow = searchParams.get("workflow");
        if (requestedWorkflow && workflowItems.some((item) => item.id === requestedWorkflow)) {
          setWorkflowIds([requestedWorkflow]);
        }
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [searchParams]);

  useEffect(() => {
    if (!projectId) {
      setProjectWorkflows([]);
      return;
    }
    api
      .listProjectWorkflows(projectId)
      .then(setProjectWorkflows)
      .catch((err: Error) => setError(err.message));
  }, [projectId]);

  const effectiveCount = useMemo(() => {
    const ids = new Set(workflowIds);
    if (projectId && inheritProjectWorkflows) {
      projectWorkflows.forEach((workflow) => ids.add(workflow.id));
    }
    return ids.size;
  }, [inheritProjectWorkflows, projectId, projectWorkflows, workflowIds]);

  function toggleWorkflow(workflowId: string) {
    setWorkflowIds((current) =>
      current.includes(workflowId)
        ? current.filter((id) => id !== workflowId)
        : [...current, workflowId],
    );
  }

  async function createConversation(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const conversation = await api.createConversation({
        title: title.trim() || null,
        project_id: projectId || null,
        workflow_ids: workflowIds,
        inherit_project_workflows: Boolean(projectId && inheritProjectWorkflows),
        ...(modelSettingsEdited
          ? { model_name: modelName.trim() || null, temperature }
          : {}),
      });
      navigate(`/conversations/${conversation.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the chat");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <div className="page-state">Loading chat setup…</div>;

  return (
    <div className="page page-narrow">
      <header className="page-header">
        <div>
          <Link className="back-link" to="/conversations">
            ← Back to chats
          </Link>
          <p className="eyebrow accent">New chat</p>
          <h1>Start with the right context.</h1>
          <p className="lede compact">
            Combine workflows directly, and optionally file the chat inside a project.
          </p>
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <form className="panel stacked-form conversation-creator" onSubmit={createConversation}>
        <div className="form-row">
          <label>
            Chat title
            <input
              autoFocus
              maxLength={200}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Untitled until your first message"
              value={title}
            />
          </label>
          <label>
            Project (optional)
            <select value={projectId} onChange={(event) => setProjectId(event.target.value)}>
              <option value="">No project — standalone chat</option>
              {projects.map((project) => (
                <option value={project.id} key={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        {projectId && (
          <label className="check-row">
            <input
              checked={inheritProjectWorkflows}
              onChange={(event) => setInheritProjectWorkflows(event.target.checked)}
              type="checkbox"
            />
            <span>
              Use workflows attached to this project
              <small>
                {projectWorkflows.length
                  ? `${projectWorkflows.length} project workflow${projectWorkflows.length === 1 ? "" : "s"} will be included.`
                  : "This project has no attached workflows yet."}
              </small>
            </span>
          </label>
        )}

        <fieldset className="workflow-picker">
          <legend>Direct workflows</legend>
          <p>
            Select any additional workflows for this chat. Direct workflows remain
            attached even if you move the chat later.
          </p>
          <div className="workflow-choice-grid">
            {workflows.map((workflow) => (
              <label
                className={
                  workflowIds.includes(workflow.id)
                    ? "workflow-choice selected"
                    : "workflow-choice"
                }
                key={workflow.id}
              >
                <input
                  checked={workflowIds.includes(workflow.id)}
                  onChange={() => toggleWorkflow(workflow.id)}
                  type="checkbox"
                />
                <span>
                  <strong>{workflow.name}</strong>
                  <small>{workflow.description || "Reusable AI configuration"}</small>
                </span>
              </label>
            ))}
          </div>
          {!workflows.length && (
            <div className="empty-card">
              <strong>No workflows in the library</strong>
              <p>You can start a general chat now or create a reusable workflow.</p>
              <Link className="card-link empty-card-link" to="/workflows?new=1">
                Create a workflow →
              </Link>
            </div>
          )}
        </fieldset>

        <details className="advanced-settings">
          <summary>Model settings</summary>
          <p className="form-note">
            Until changed here, the first active workflow supplies these defaults.
          </p>
          <div className="form-row">
            <label>
              Gemini model override
              <input
                value={modelName}
                onChange={(event) => {
                  setModelName(event.target.value);
                  setModelSettingsEdited(true);
                }}
                placeholder="Use environment default"
              />
            </label>
            <label>
              Temperature <output>{temperature.toFixed(1)}</output>
              <input
                max="2"
                min="0"
                onChange={(event) => {
                  setTemperature(Number(event.target.value));
                  setModelSettingsEdited(true);
                }}
                step="0.1"
                type="range"
                value={temperature}
              />
            </label>
          </div>
        </details>

        <div className="creator-footer">
          <span>
            {effectiveCount
              ? `${effectiveCount} active workflow${effectiveCount === 1 ? "" : "s"}`
              : "General chat · no workflow"}
          </span>
          <button className="primary-button" disabled={saving}>
            {saving ? "Creating…" : "Create chat"}
          </button>
        </div>
      </form>
    </div>
  );
}
