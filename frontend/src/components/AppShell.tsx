import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { api } from "../api/client";
import type { Conversation, Project } from "../types";
import { BranchHoverPreview } from "./BranchHoverPreview";
import { ConversationActions } from "./ConversationActions";

export function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loadError, setLoadError] = useState("");
  const [hoveredConversationId, setHoveredConversationId] = useState<string | null>(
    null,
  );

  useEffect(() => {
    let cancelled = false;
    const loadSidebar = () =>
      Promise.all([api.listProjects(), api.listConversations()])
      .then(([projectItems, conversationItems]) => {
        if (!cancelled) {
          setProjects(projectItems);
          setConversations(conversationItems);
          setLoadError("");
        }
      })
      .catch(() => {
        if (!cancelled) setLoadError("API unavailable");
      });
    void loadSidebar();
    window.addEventListener("conversations-updated", loadSidebar);
    return () => {
      cancelled = true;
      window.removeEventListener("conversations-updated", loadSidebar);
    };
  }, [location.pathname]);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <NavLink className="brand" to="/projects">
          <span className="brand-mark">W</span>
          <span>
            <strong>AI Workspace</strong>
            <small>Persistent thinking</small>
          </span>
        </NavLink>

        <NavLink className="new-project-link" to="/conversations/new">
          <span>＋</span> New chat
        </NavLink>

        <nav className="primary-nav" aria-label="Workspace navigation">
          <NavLink to="/conversations">
            <span className="nav-symbol">C</span>
            <span>Chats</span>
          </NavLink>
          <NavLink to="/workflows">
            <span className="nav-symbol">W</span>
            <span>Workflows</span>
          </NavLink>
          <NavLink to="/projects" end>
            <span className="nav-symbol">P</span>
            <span>Projects</span>
          </NavLink>
        </nav>

        <div className="sidebar-sections">
          <div className="sidebar-section">
            <div className="sidebar-section-heading">
              <p className="eyebrow">Chats</p>
              <NavLink aria-label="New chat" to="/conversations/new">
                ＋
              </NavLink>
            </div>
            <nav className="project-nav chat-nav" aria-label="Chats">
              {conversations.map((conversation) => (
                <div
                  className="sidebar-chat-item"
                  key={conversation.id}
                  onMouseEnter={() => setHoveredConversationId(conversation.id)}
                  onMouseLeave={() => setHoveredConversationId(null)}
                >
                  <NavLink
                    title={conversation.title}
                    to={`/conversations/${conversation.id}`}
                  >
                    <span className="nav-dot chat-dot" />
                    <span>{conversation.title}</span>
                  </NavLink>
                  <ConversationActions
                    conversation={conversation}
                    onDeleted={(deleted) => {
                      setConversations((current) =>
                        current.filter((item) => item.id !== deleted.id),
                      );
                      if (
                        location.pathname.startsWith(
                          `/conversations/${deleted.id}`,
                        )
                      ) {
                        navigate("/conversations", { replace: true });
                      }
                    }}
                    onUpdated={(updated) =>
                      setConversations((current) =>
                        current.map((item) =>
                          item.id === updated.id ? updated : item,
                        ),
                      )
                    }
                    onMenuOpenChange={(open) => {
                      if (open) setHoveredConversationId(null);
                    }}
                  />
                  <BranchHoverPreview
                    conversationId={conversation.id}
                    mainBranchId={conversation.main_branch_id}
                    visible={hoveredConversationId === conversation.id}
                  />
                </div>
              ))}
              {!conversations.length && !loadError && (
                <span className="sidebar-empty">No chats yet</span>
              )}
            </nav>
          </div>

          <div className="sidebar-section">
            <div className="sidebar-section-heading">
              <p className="eyebrow">Projects</p>
              <NavLink aria-label="New project" to="/projects?new=1">
                ＋
              </NavLink>
            </div>
            <nav className="project-nav" aria-label="Projects">
              {projects.map((project) => (
                <NavLink key={project.id} to={`/projects/${project.id}`}>
                  <span className="nav-dot" />
                  <span>{project.name}</span>
                </NavLink>
              ))}
              {!projects.length && !loadError && (
                <span className="sidebar-empty">No projects yet</span>
              )}
              {loadError && <span className="sidebar-error">{loadError}</span>}
            </nav>
          </div>
        </div>

        <div className="sidebar-footer">
          <span className="status-dot" /> Gemini branching ready
        </div>
      </aside>
      <main className="main-workspace">
        <Outlet />
      </main>
    </div>
  );
}
