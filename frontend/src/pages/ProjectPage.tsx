import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api/client";
import { ConversationActions } from "../components/ConversationActions";
import type { Conversation, Project, Workflow } from "../types";

export function ProjectPage() {
  const { projectId = "" } = useParams();
  const [project, setProject] = useState<Project | null>(null);
  const [attachedWorkflows, setAttachedWorkflows] = useState<Workflow[]>([]);
  const [allWorkflows, setAllWorkflows] = useState<Workflow[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [workflowToAttach, setWorkflowToAttach] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);

  async function loadProject() {
    const [projectResult, attachedResult, workflowResult, conversationResult] =
      await Promise.all([
        api.getProject(projectId),
        api.listProjectWorkflows(projectId),
        api.listWorkflows(),
        api.listConversations({ projectId }),
      ]);
    setProject(projectResult);
    setAttachedWorkflows(attachedResult);
    setAllWorkflows(workflowResult);
    setConversations(conversationResult);
  }

  useEffect(() => {
    loadProject().catch((err: Error) => setError(err.message));
  }, [projectId]);

  const availableWorkflows = useMemo(() => {
    const attachedIds = new Set(attachedWorkflows.map((workflow) => workflow.id));
    return allWorkflows.filter((workflow) => !attachedIds.has(workflow.id));
  }, [allWorkflows, attachedWorkflows]);

  const workflowNames = useMemo(
    () => new Map(allWorkflows.map((workflow) => [workflow.id, workflow.name])),
    [allWorkflows],
  );

  useEffect(() => {
    setWorkflowToAttach((current) =>
      availableWorkflows.some((workflow) => workflow.id === current)
        ? current
        : availableWorkflows[0]?.id ?? "",
    );
  }, [availableWorkflows]);

  async function attachWorkflow(event: FormEvent) {
    event.preventDefault();
    if (!workflowToAttach) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await api.attachWorkflowToProject(projectId, workflowToAttach);
      await loadProject();
      setNotice("Workflow attached to this project.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not attach the workflow");
    } finally {
      setSaving(false);
    }
  }

  async function detachWorkflow(workflow: Workflow) {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await api.detachWorkflowFromProject(projectId, workflow.id);
      await loadProject();
      setNotice(`${workflow.name} was detached. Existing chats are unchanged.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not detach the workflow");
    } finally {
      setSaving(false);
    }
  }

  if (!project && !error) return <div className="page-state">Loading project…</div>;

  return (
    <div className="page">
      {error && <div className="error-banner">{error}</div>}
      {notice && <div className="success-banner">{notice}</div>}
      {project && (
        <>
          <header className="page-header">
            <div>
              <p className="eyebrow accent">Project</p>
              <h1>{project.name}</h1>
              <p className="lede compact">
                {project.description || "Add a description to explain this workspace."}
              </p>
            </div>
            <div className="header-actions">
              <Link
                className="secondary-button button-link"
                to={`/workflows?new=1&project=${projectId}`}
              >
                New workflow
              </Link>
              <Link
                className="primary-button button-link"
                to={`/conversations/new?project=${projectId}`}
              >
                New chat
              </Link>
            </div>
          </header>

          <section className="panel project-workflow-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Project context</p>
                <h2>Attached workflows</h2>
              </div>
              <span className="count-badge">{attachedWorkflows.length}</span>
            </div>
            <p className="section-description">
              New project chats can inherit these workflows. The workflows remain
              available globally and may be attached to other projects too.
            </p>

            <div className="attached-workflow-grid">
              {attachedWorkflows.map((workflow) => (
                <div className="list-card attached-workflow" key={workflow.id}>
                  <Link className="list-card-main" to={`/workflows/${workflow.id}`}>
                    <span className="list-icon violet">W</span>
                    <span className="list-copy">
                      <strong>{workflow.name}</strong>
                      <small>{workflow.description || "Global workflow"}</small>
                    </span>
                  </Link>
                  <button
                    className="text-button danger-text"
                    disabled={saving}
                    onClick={() => detachWorkflow(workflow)}
                    type="button"
                  >
                    Detach
                  </button>
                </div>
              ))}
              {!attachedWorkflows.length && (
                <div className="empty-card compact-empty">
                  No workflows are attached to this project yet.
                </div>
              )}
            </div>

            {availableWorkflows.length > 0 && (
              <form className="attach-workflow-form" onSubmit={attachWorkflow}>
                <label>
                  Add from the global library
                  <select
                    value={workflowToAttach}
                    onChange={(event) => setWorkflowToAttach(event.target.value)}
                  >
                    {availableWorkflows.map((workflow) => (
                      <option value={workflow.id} key={workflow.id}>
                        {workflow.name}
                      </option>
                    ))}
                  </select>
                </label>
                <button className="secondary-button" disabled={saving}>
                  {saving ? "Updating…" : "Attach workflow"}
                </button>
              </form>
            )}
          </section>

          <section className="project-conversations">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Filed here</p>
                <h2>Chats</h2>
              </div>
              <span className="count-badge">{conversations.length}</span>
            </div>
            <div className="item-list">
              {conversations.map((conversation) => {
                const names = (conversation.effective_workflow_ids ?? [])
                  .map((id) => workflowNames.get(id))
                  .filter(Boolean)
                  .join(" + ");
                return (
                  <div
                    className="list-card"
                    key={conversation.id}
                  >
                    <Link
                      className="list-card-main"
                      to={`/conversations/${conversation.id}`}
                    >
                      <span className="list-icon mint">C</span>
                      <span className="list-copy">
                        <strong>{conversation.title}</strong>
                        <small>
                          {names || "No workflow"} · Updated{" "}
                          {new Date(conversation.updated_at).toLocaleDateString()}
                        </small>
                      </span>
                      <span className="list-arrow">→</span>
                    </Link>
                    <ConversationActions
                      conversation={conversation}
                      onDeleted={(deleted) => {
                        setConversations((current) =>
                          current.filter((item) => item.id !== deleted.id),
                        );
                        setNotice(`${deleted.title} was deleted.`);
                      }}
                      onUpdated={(updated) =>
                        setConversations((current) =>
                          current.map((item) =>
                            item.id === updated.id ? updated : item,
                          ),
                        )
                      }
                    />
                  </div>
                );
              })}
              {!conversations.length && (
                <div className="empty-card">
                  <strong>No chats in this project</strong>
                  <p>Start one with the project workflows, or add direct workflows.</p>
                  <Link
                    className="card-link empty-card-link"
                    to={`/conversations/new?project=${projectId}`}
                  >
                    Start a chat →
                  </Link>
                </div>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
