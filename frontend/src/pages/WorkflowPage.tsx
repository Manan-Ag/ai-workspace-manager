import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import type { WorkflowInput } from "../types";

const initialInput: WorkflowInput = {
  name: "",
  description: "",
  system_prompt: "",
  prompt_template: "",
  model_name: null,
  temperature: 0.7,
};

export function WorkflowPage() {
  const { workflowId = "" } = useParams();
  const navigate = useNavigate();
  const [input, setInput] = useState<WorkflowInput>(initialInput);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api
      .getWorkflow(workflowId)
      .then((workflow) =>
        setInput({
          name: workflow.name,
          description: workflow.description,
          system_prompt: workflow.system_prompt,
          prompt_template: workflow.prompt_template,
          model_name: workflow.model_name,
          temperature: workflow.temperature,
        }),
      )
      .catch((err: Error) => setError(err.message));
  }, [workflowId]);

  async function saveWorkflow(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setSaved(false);
    setError("");
    try {
      await api.updateWorkflow(workflowId, input);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the workflow");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page page-narrow">
      <header className="page-header">
        <div>
          <Link className="back-link" to="/workflows">
            ← Back to workflow library
          </Link>
          <p className="eyebrow accent">Global workflow</p>
          <h1>{input.name || "Workflow"}</h1>
          <p className="lede compact">
            Changes apply wherever this workflow is used without rewriting stored
            messages.
          </p>
        </div>
        <button
          className="primary-button"
          onClick={() => navigate(`/conversations/new?workflow=${workflowId}`)}
          type="button"
        >
          Start a chat
        </button>
      </header>
      {error && <div className="error-banner">{error}</div>}
      {saved && <div className="success-banner">Workflow saved.</div>}

      <form className="panel stacked-form workflow-editor" onSubmit={saveWorkflow}>
        <div className="form-row">
          <label>
            Name
            <input
              required
              value={input.name}
              onChange={(event) => setInput({ ...input, name: event.target.value })}
            />
          </label>
          <label>
            Description
            <input
              value={input.description}
              onChange={(event) =>
                setInput({ ...input, description: event.target.value })
              }
            />
          </label>
        </div>
        <label>
          System prompt
          <textarea
            rows={8}
            value={input.system_prompt}
            onChange={(event) =>
              setInput({ ...input, system_prompt: event.target.value })
            }
          />
        </label>
        <label>
          Reusable prompt template
          <textarea
            rows={6}
            value={input.prompt_template}
            onChange={(event) =>
              setInput({ ...input, prompt_template: event.target.value })
            }
          />
          <small>Simple variables such as {"{{company}}"} are preserved.</small>
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
              max="2"
              min="0"
              onChange={(event) =>
                setInput({ ...input, temperature: Number(event.target.value) })
              }
              step="0.1"
              type="range"
              value={input.temperature}
            />
          </label>
        </div>
        <div className="form-actions">
          <button className="primary-button" disabled={saving} type="submit">
            {saving ? "Saving…" : "Save workflow"}
          </button>
          <button
            className="secondary-button"
            onClick={() => navigate(`/conversations/new?workflow=${workflowId}`)}
            type="button"
          >
            Use in a new chat
          </button>
        </div>
      </form>
    </div>
  );
}
