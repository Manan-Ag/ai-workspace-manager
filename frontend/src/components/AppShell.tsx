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
  const [tourStep, setTourStep] = useState<number | null>(() =>
    window.localStorage.getItem("ai-workspace-tour-v1") === "pending" ? 0 : null,
  );

  const tourSteps = [
    {
      eyebrow: "Welcome",
      title: "This sample chat is your two-minute tour.",
      body: "It is already filled with a realistic product-planning conversation, so you can explore the app before writing anything.",
    },
    {
      eyebrow: "The main idea",
      title: "Branch from an answer without losing the original.",
      body: "Every Gemini answer offers Start branch. A branch keeps the relevant context and becomes a focused path beside the main trunk.",
    },
    {
      eyebrow: "Try the tree",
      title: "Switch between Main and Recruiter demo path.",
      body: "Use the branch tree on the left of this chat. The sample branch shows how one broad launch discussion becomes a recruiter-focused thread.",
    },
    {
      eyebrow: "Your workspace",
      title: "Now make it yours.",
      body: "Create chats with or without projects, save reusable workflows, and search every message. Your guest data is isolated from every other visitor.",
    },
  ];

  function closeTour() {
    window.localStorage.setItem("ai-workspace-tour-v1", "complete");
    setTourStep(null);
  }

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
      {tourStep !== null && (
        <div className="product-tour" role="dialog" aria-modal="true">
          <section className="product-tour-card">
            <button className="product-tour-close" onClick={closeTour} aria-label="Skip tour">
              ×
            </button>
            <div className="product-tour-progress" aria-label={`Step ${tourStep + 1} of ${tourSteps.length}`}>
              {tourSteps.map((_, index) => (
                <span className={index <= tourStep ? "active" : ""} key={index} />
              ))}
            </div>
            <p className="eyebrow accent">{tourSteps[tourStep].eyebrow}</p>
            <h2>{tourSteps[tourStep].title}</h2>
            <p>{tourSteps[tourStep].body}</p>
            <div className="product-tour-actions">
              {tourStep > 0 && (
                <button className="text-button" onClick={() => setTourStep(tourStep - 1)}>
                  Back
                </button>
              )}
              <button
                className="primary-button"
                onClick={() =>
                  tourStep === tourSteps.length - 1
                    ? closeTour()
                    : setTourStep(tourStep + 1)
                }
              >
                {tourStep === tourSteps.length - 1 ? "Start exploring" : "Next"}
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
