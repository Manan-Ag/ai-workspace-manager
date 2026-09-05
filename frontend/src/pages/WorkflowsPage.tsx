import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import type { Workflow, WorkflowInput } from "../types";

const emptyWorkflow: WorkflowInput = {
  name: "",
  description: "",
  system_prompt: "",
  prompt_template: "",
  model_name: null,
  temperature: 0.7,
};

export function WorkflowsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [input, setInput] = useState<WorkflowInput>(emptyWorkflow);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const creating =
    searchParams.get("new") === "1" || (!loading && workflows.length === 0);
  const attachToProject = searchParams.get("project");

  useEffect(() => {
    api
      .listWorkflows()
      .then(setWorkflows)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  async function createWorkflow(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const workflow = await api.createWorkflow(input);
      if (attachToProject) {
        await api.attachWorkflowToProject(attachToProject, workflow.id);
      }
      navigate(`/workflows/${workflow.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the workflow");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page">
      <header className="page-header hero-header">
        <div>
          <p className="eyebrow accent">Global library</p>
          <h1>Build a workflow once. Use it anywhere.</h1>
          <p className="lede">
            Workflows hold reusable instructions and model settings. Attach them to
            projects or combine them directly in a standalone chat.
          </p>
        </div>
        {!creating && (
          <button
            className="primary-button"
            onClick={() => setSearchParams({ new: "1" })}
          >
            New workflow
          </button>
        )}
      </header>

      {error && <div className="error-banner">{error}</div>}

      {creating && (
        <section className="panel form-panel workflow-create-panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Reusable configuration</p>
              <h2>Create a workflow</h2>
            </div>
            {workflows.length > 0 && (
              <button className="text-button" onClick={() => setSearchParams({})}>
                Cancel
              </button>
            )}
          </div>
          {attachToProject && (
            <p className="form-note">
              This workflow will also be attached to the project you came from.
            </p>
          )}
          <form className="stacked-form" onSubmit={createWorkflow}>
            <div className="form-row">
              <label>
                Name
                <input
                  autoFocus
                  required
                  value={input.name}
                  onChange={(event) => setInput({ ...input, name: event.target.value })}
                  placeholder="Fundamental Equity Analyst"
                />
              </label>
              <label>
                Description
                <input
                  value={input.description}
                  onChange={(event) =>
                    setInput({ ...input, description: event.target.value })
                  }
                  placeholder="What this workflow is best at"
                />
              </label>
            </div>
            <label>
              System prompt
              <textarea
                rows={5}
                value={input.system_prompt}
                onChange={(event) =>
                  setInput({ ...input, system_prompt: event.target.value })
                }
                placeholder="You are a careful research assistant…"
              />
            </label>
            <label>
              Reusable prompt template
              <textarea
                rows={4}
                value={input.prompt_template}
                onChange={(event) =>
                  setInput({ ...input, prompt_template: event.target.value })
                }
                placeholder="Analyze {{company}} with emphasis on {{focus_area}}."
              />
            </label>
            <div className="form-row">
              <label>
                Gemini model override
                <input
                  value={input.model_name ?? ""}
                  onChange={(event) =>
                    setInput({ ...input, model_name: event.target.value || null })
                  }
                  placeholder="Use environment default"
                />
              </label>
              <label>
                Temperature <output>{input.temperature.toFixed(1)}</output>
                <input
                  type="range"
                  min="0"
                  max="2"
                  step="0.1"
                  value={input.temperature}
                  onChange={(event) =>
                    setInput({ ...input, temperature: Number(event.target.value) })
                  }
                />
              </label>
            </div>
            <button className="primary-button align-start" disabled={saving}>
              {saving ? "Saving…" : "Save to library"}
            </button>
          </form>
        </section>
      )}

      {loading && !creating && <div className="empty-card">Loading workflows…</div>}

      {!creating && !loading && (
        <section>
          <div className="section-heading">
            <div>
              <p className="eyebrow">Available everywhere</p>
              <h2>Workflows</h2>
            </div>
            <span className="count-badge">{workflows.length}</span>
          </div>
          <div className="card-grid">
            {workflows.map((workflow) => (
              <Link className="project-card workflow-card" key={workflow.id} to={`/workflows/${workflow.id}`}>
                <span className="card-icon">W</span>
                <strong>{workflow.name}</strong>
                <p>{workflow.description || "No description yet."}</p>
                <span className="card-link">Edit workflow →</span>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
