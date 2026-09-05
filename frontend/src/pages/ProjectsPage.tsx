import { FormEvent, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import type { Project } from "../types";

export function ProjectsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const creating = searchParams.get("new") === "1" || projects.length === 0;

  useEffect(() => {
    api.listProjects().then(setProjects).catch((err: Error) => setError(err.message));
  }, []);

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const project = await api.createProject({ name, description });
      navigate(`/projects/${project.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the project");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page page-narrow">
      <header className="page-header hero-header">
        <div>
          <p className="eyebrow accent">Workspace</p>
          <h1>Turn ongoing AI work into something you can return to.</h1>
          <p className="lede">
            Organize reusable workflows, persistent conversations, and branching
            lines of thought.
          </p>
        </div>
        {!creating && (
          <button className="primary-button" onClick={() => setSearchParams({ new: "1" })}>
            New project
          </button>
        )}
      </header>

      {error && <div className="error-banner">{error}</div>}

      {creating && (
        <section className="panel form-panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">First step</p>
              <h2>Create a project</h2>
            </div>
            {projects.length > 0 && (
              <button className="text-button" onClick={() => setSearchParams({})}>
                Cancel
              </button>
            )}
          </div>
          <form onSubmit={handleCreate} className="stacked-form">
            <label>
              Project name
              <input
                autoFocus
                maxLength={120}
                onChange={(event) => setName(event.target.value)}
                placeholder="e.g. Equity Research"
                required
                value={name}
              />
            </label>
            <label>
              Description
              <textarea
                maxLength={4000}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="What long-running work belongs here?"
                rows={4}
                value={description}
              />
            </label>
            <div className="form-actions">
              <button className="primary-button" disabled={submitting} type="submit">
                {submitting ? "Creating…" : "Create project"}
              </button>
            </div>
          </form>
        </section>
      )}

      {!creating && (
        <section>
          <div className="section-heading">
            <h2>Your projects</h2>
            <span className="count-badge">{projects.length}</span>
          </div>
          <div className="card-grid">
            {projects.map((project) => (
              <button
                className="project-card"
                key={project.id}
                onClick={() => navigate(`/projects/${project.id}`)}
              >
                <span className="card-icon">P</span>
                <strong>{project.name}</strong>
                <p>{project.description || "No description yet."}</p>
                <span className="card-link">Open project →</span>
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

