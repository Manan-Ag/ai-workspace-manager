import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import { BranchHoverPreview } from "../components/BranchHoverPreview";
import { ConversationActions } from "../components/ConversationActions";
import type { Conversation, Project, Workflow } from "../types";

export function ConversationsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [hoveredConversationId, setHoveredConversationId] = useState<string | null>(
    null,
  );
  const standalone = searchParams.get("scope") === "standalone";
  const searchQuery = searchParams.get("q")?.trim() ?? "";
  const [searchDraft, setSearchDraft] = useState(searchQuery);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      api.listConversations({
        standalone: standalone || undefined,
        search: searchQuery || undefined,
      }),
      api.listProjects(),
      api.listWorkflows(),
    ])
      .then(([conversationItems, projectItems, workflowItems]) => {
        if (cancelled) return;
        setConversations(conversationItems);
        setProjects(projectItems);
        setWorkflows(workflowItems);
        setError("");
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [searchQuery, standalone]);

  function updateSearchParams(options: { standalone: boolean; query: string }) {
    const next: Record<string, string> = {};
    if (options.standalone) next.scope = "standalone";
    if (options.query.trim()) next.q = options.query.trim();
    setSearchParams(next, { replace: true });
  }

  useEffect(() => {
    if (searchDraft.trim() === searchQuery) return;
    const timer = window.setTimeout(() => {
      updateSearchParams({ standalone, query: searchDraft });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [searchDraft, searchQuery, standalone]);

  const projectNames = useMemo(
    () => new Map(projects.map((project) => [project.id, project.name])),
    [projects],
  );
  const workflowNames = useMemo(
    () => new Map(workflows.map((workflow) => [workflow.id, workflow.name])),
    [workflows],
  );

  return (
    <div className="page">
      <header className="page-header hero-header">
        <div>
          <p className="eyebrow accent">Chats</p>
          <h1>Pick up any line of thought.</h1>
          <p className="lede">
            Chats can live inside a project or stand alone. Their workflow context
            and branches stay attached wherever you file them.
          </p>
        </div>
        <Link className="primary-button button-link" to="/conversations/new">
          New chat
        </Link>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <div className="chat-search" role="search">
        <label htmlFor="chat-search-input">Search every chat</label>
        <div className="chat-search-row">
          <input
            id="chat-search-input"
            onChange={(event) => setSearchDraft(event.target.value)}
            placeholder="Search titles and message content…"
            type="search"
            value={searchDraft}
          />
          {(searchDraft || searchQuery) && (
            <button
              className="secondary-button"
              onClick={() => {
                setSearchDraft("");
                updateSearchParams({ standalone, query: "" });
              }}
              type="button"
            >
              Clear
            </button>
          )}
        </div>
        <small>
          Results update as you type and include every saved message in every branch.
        </small>
      </div>

      <div className="filter-tabs" aria-label="Chat filters">
        <button
          className={!standalone ? "active" : ""}
          onClick={() =>
            updateSearchParams({ standalone: false, query: searchDraft })
          }
          type="button"
        >
          All chats
        </button>
        <button
          className={standalone ? "active" : ""}
          onClick={() =>
            updateSearchParams({ standalone: true, query: searchDraft })
          }
          type="button"
        >
          Standalone
        </button>
      </div>

      {loading ? (
        <div className="empty-card">Loading chats…</div>
      ) : (
        <div className="item-list conversation-list">
          {conversations.map((conversation) => {
            const activeWorkflowIds =
              conversation.effective_workflow_ids ?? conversation.workflow_ids ?? [];
            const workflowLabel = activeWorkflowIds
              .map((id) => workflowNames.get(id))
              .filter(Boolean)
              .join(" + ");
            return (
              <div
                className="list-card conversation-list-card"
                key={conversation.id}
                onMouseEnter={() => setHoveredConversationId(conversation.id)}
                onMouseLeave={() => setHoveredConversationId(null)}
              >
                <Link
                  className="list-card-main"
                  to={`/conversations/${conversation.id}`}
                >
                  <span className="list-icon mint">C</span>
                  <span className="list-copy">
                    <strong>{conversation.title}</strong>
                    <small>
                      {conversation.project_id
                        ? projectNames.get(conversation.project_id) ?? "Project"
                        : "Standalone"}
                      {workflowLabel ? ` · ${workflowLabel}` : " · No workflow"}
                    </small>
                  </span>
                  <span className="conversation-updated">
                    {new Date(conversation.updated_at).toLocaleDateString()}
                  </span>
                  <span className="list-arrow">→</span>
                </Link>
                <ConversationActions
                  conversation={conversation}
                  onDeleted={(deleted) =>
                    setConversations((current) =>
                      current.filter((item) => item.id !== deleted.id),
                    )
                  }
                  onUpdated={(updated) =>
                    setConversations((current) =>
                      current.map((item) =>
                        item.id === updated.id ? updated : item,
                      ),
                    )
                  }
                />
                <BranchHoverPreview
                  conversationId={conversation.id}
                  mainBranchId={conversation.main_branch_id}
                  visible={hoveredConversationId === conversation.id}
                />
              </div>
            );
          })}
          {!conversations.length && !error && (
            <div className="empty-card">
              <strong>
                {searchQuery
                  ? `No chats match “${searchQuery}”`
                  : standalone
                    ? "No standalone chats"
                    : "No chats yet"}
              </strong>
              {searchQuery ? (
                <p>Try a shorter phrase or search all chats.</p>
              ) : (
                <>
                  <p>
                    Start a general chat or add reusable workflows, then branch as
                    you go.
                  </p>
                  <Link
                    className="card-link empty-card-link"
                    to="/conversations/new"
                  >
                    Create a chat →
                  </Link>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
