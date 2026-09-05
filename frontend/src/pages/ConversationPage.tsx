import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import { ConversationBranches } from "../components/ConversationBranches";
import { ConversationActions } from "../components/ConversationActions";
import { MarkdownContent } from "../components/MarkdownContent";
import type {
  BranchSuggestion,
  ChatTurnResponse,
  Conversation,
  ConversationBranch,
  Message,
  Project,
  Workflow,
} from "../types";

function replaceBranch(
  branches: ConversationBranch[],
  updated: ConversationBranch,
) {
  const exists = branches.some((branch) => branch.id === updated.id);
  return exists
    ? branches.map((branch) => (branch.id === updated.id ? updated : branch))
    : [...branches, updated];
}

function formatDuration(milliseconds: number) {
  const totalSeconds = Math.max(0, milliseconds) / 1000;
  if (totalSeconds < 60) return `${totalSeconds.toFixed(1)}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = (totalSeconds % 60).toFixed(1).padStart(4, "0");
  return `${minutes}:${seconds}`;
}

function messageGenerationDuration(message: Message) {
  const value = message.metadata.generation_duration_ms;
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : null;
}

export function ConversationPage() {
  const { conversationId = "", branchId } = useParams();
  const navigate = useNavigate();
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [branches, setBranches] = useState<ConversationBranch[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [suggestions, setSuggestions] = useState<BranchSuggestion[]>([]);
  const [composer, setComposer] = useState("");
  const [pendingUserMessage, setPendingUserMessage] = useState<string | null>(
    null,
  );
  const [workflowToAttach, setWorkflowToAttach] = useState("");
  const [contextOpen, setContextOpen] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [selectedContextTopics, setSelectedContextTopics] = useState<string[]>([]);
  const [expandingContext, setExpandingContext] = useState(false);
  const [generationStartedAt, setGenerationStartedAt] = useState<number | null>(
    null,
  );
  const [generationElapsedMs, setGenerationElapsedMs] = useState(0);
  const pendingAnswerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (generationStartedAt === null) return;
    const updateElapsed = () =>
      setGenerationElapsedMs(performance.now() - generationStartedAt);
    updateElapsed();
    const timer = window.setInterval(updateElapsed, 100);
    return () => window.clearInterval(timer);
  }, [generationStartedAt]);

  useEffect(() => {
    if (!pendingUserMessage) return;
    const frame = window.requestAnimationFrame(() => {
      pendingAnswerRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [pendingUserMessage]);

  async function loadConversation() {
    const [conversationResult, workflowResult, branchResult, suggestionResult] =
      await Promise.all([
        api.getConversation(conversationId),
        api.listWorkflows(),
        api.listBranches(conversationId),
        api.listBranchSuggestions(conversationId),
      ]);
    const projectResult = conversationResult.project_id
      ? await api.getProject(conversationResult.project_id)
      : null;

    setConversation(conversationResult);
    setProject(projectResult);
    setWorkflows(workflowResult);
    setBranches(branchResult);
    setSuggestions(suggestionResult);

    if (!branchId) {
      const mainBranchId =
        conversationResult.main_branch_id ??
        branchResult.find((branch) => branch.is_main)?.id;
      if (mainBranchId) {
        navigate(
          `/conversations/${conversationId}/branches/${mainBranchId}`,
          { replace: true },
        );
      }
    }
  }

  useEffect(() => {
    setLoading(true);
    setError("");
    loadConversation()
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [conversationId]);

  useEffect(() => {
    setPendingUserMessage(null);
    if (!branchId) {
      setMessages([]);
      return;
    }
    setError("");
    api
      .listBranchMessages(conversationId, branchId)
      .then(setMessages)
      .catch((err: Error) => setError(err.message));
  }, [branchId, conversationId]);

  const activeBranch = useMemo(
    () => branches.find((branch) => branch.id === branchId) ?? null,
    [branchId, branches],
  );
  const workflowNames = useMemo(() => {
    const byId = new Map(workflows.map((workflow) => [workflow.id, workflow.name]));
    return (conversation?.effective_workflow_ids ?? [])
      .map((id) => byId.get(id))
      .filter((name): name is string => Boolean(name));
  }, [conversation, workflows]);
  const directWorkflows = useMemo(
    () =>
      workflows.filter((workflow) =>
        conversation?.workflow_ids.includes(workflow.id),
      ),
    [conversation, workflows],
  );
  const inheritedWorkflows = useMemo(
    () =>
      workflows.filter(
        (workflow) =>
          conversation?.effective_workflow_ids.includes(workflow.id) &&
          !conversation.workflow_ids.includes(workflow.id),
      ),
    [conversation, workflows],
  );
  const availableDirectWorkflows = useMemo(
    () =>
      workflows.filter(
        (workflow) => !conversation?.workflow_ids.includes(workflow.id),
      ),
    [conversation, workflows],
  );
  const visibleSuggestion = useMemo(
    () =>
      suggestions.find(
        (suggestion) => suggestion.source_branch_id === activeBranch?.id,
      ) ?? null,
    [activeBranch, suggestions],
  );

  useEffect(() => {
    setWorkflowToAttach((current) =>
      availableDirectWorkflows.some((workflow) => workflow.id === current)
        ? current
        : availableDirectWorkflows[0]?.id ?? "",
    );
  }, [availableDirectWorkflows]);
  const activeBranchHasPendingSuggestion = suggestions.some(
    (suggestion) => suggestion.source_branch_id === activeBranch?.id,
  );

  useEffect(() => {
    setSelectedContextTopics([]);
  }, [branchId]);

  async function refreshBranchState() {
    const [conversationResult, branchResult, suggestionResult] = await Promise.all([
      api.getConversation(conversationId),
      api.listBranches(conversationId),
      api.listBranchSuggestions(conversationId),
    ]);
    setConversation(conversationResult);
    setBranches(branchResult);
    setSuggestions(suggestionResult);
  }

  function scheduleNewBranchTitleRefresh() {
    [1500, 5000, 12000, 25000].forEach((delay) => {
      window.setTimeout(() => {
        Promise.all([
          api.getConversation(conversationId),
          api.listBranches(conversationId),
        ])
          .then(([conversationResult, branchResult]) => {
            setConversation(conversationResult);
            setBranches(branchResult);
          })
          .catch(() => undefined);
      }, delay);
    });
  }

  async function attachConversationWorkflow(event: FormEvent) {
    event.preventDefault();
    if (!workflowToAttach) return;
    setSending(true);
    setError("");
    try {
      await api.attachWorkflowToConversation(conversationId, workflowToAttach);
      setConversation(await api.getConversation(conversationId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not attach the workflow");
    } finally {
      setSending(false);
    }
  }

  async function detachConversationWorkflow(workflow: Workflow) {
    setSending(true);
    setError("");
    try {
      await api.detachWorkflowFromConversation(conversationId, workflow.id);
      setConversation(await api.getConversation(conversationId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not detach the workflow");
    } finally {
      setSending(false);
    }
  }

  async function setProjectWorkflowInheritance(enabled: boolean) {
    setSending(true);
    setError("");
    try {
      setConversation(
        await api.updateConversation(conversationId, {
          inherit_project_workflows: enabled,
        }),
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not update project workflows",
      );
    } finally {
      setSending(false);
    }
  }

  function applyChatResult(result: ChatTurnResponse) {
    setBranches((current) => replaceBranch(current, result.branch));
    if (result.kind === "branch_suggested") {
      setSuggestions((current) => {
        const withoutCurrent = current.filter(
          (suggestion) => suggestion.id !== result.suggestion.id,
        );
        return [...withoutCurrent, result.suggestion];
      });
      return;
    }

    if (result.branch.id === branchId) {
      setMessages((current) => [
        ...current.filter(
          (message) =>
            message.id !== result.user_message.id &&
            message.id !== result.assistant_message.id,
        ),
        result.user_message,
        result.assistant_message,
      ]);
    } else {
      navigate(
        `/conversations/${conversationId}/branches/${result.branch.id}`,
      );
    }
  }

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    const content = composer.trim();
    if (!content || !activeBranch || activeBranchHasPendingSuggestion) return;
    const isFirstMainPrompt =
      activeBranch.is_main && activeBranch.head_message_id === null;
    const startedAt = performance.now();
    setComposer("");
    setPendingUserMessage(content);
    setSending(true);
    setGenerationElapsedMs(0);
    setGenerationStartedAt(startedAt);
    setError("");
    try {
      const result = await api.sendBranchMessage(
        conversationId,
        activeBranch.id,
        content,
        activeBranch.head_message_id,
      );
      applyChatResult(result);
      setPendingUserMessage(null);
      await refreshBranchState();
      if (isFirstMainPrompt && result.kind === "completed") {
        scheduleNewBranchTitleRefresh();
      }
    } catch (err) {
      setPendingUserMessage(null);
      setComposer((current) => (current.trim() ? current : content));
      setError(err instanceof Error ? err.message : "Could not send the message");
    } finally {
      setGenerationElapsedMs(performance.now() - startedAt);
      setGenerationStartedAt(null);
      setSending(false);
    }
  }

  function toggleContextTopic(topic: string) {
    setSelectedContextTopics((current) =>
      current.includes(topic)
        ? current.filter((item) => item !== topic)
        : [...current, topic],
    );
  }

  async function includeSelectedContext() {
    if (!activeBranch || !selectedContextTopics.length) return;
    setExpandingContext(true);
    setSending(true);
    setError("");
    try {
      const branch = await api.includeBranchContext(
        conversationId,
        activeBranch.id,
        selectedContextTopics,
      );
      setBranches((current) => replaceBranch(current, branch));
      setSelectedContextTopics([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not restore that context");
    } finally {
      setExpandingContext(false);
      setSending(false);
    }
  }

  async function createBranchFromAnswer(message: Message) {
    if (!activeBranch || message.role !== "assistant") return;
    setSending(true);
    setError("");
    try {
      const branch = await api.createBranch(conversationId, {
        source_branch_id: activeBranch.id,
        forked_from_message_id: message.id,
        name: `Branch from ${message.content.slice(0, 36)}`,
      });
      setBranches((current) => replaceBranch(current, branch));
      navigate(`/conversations/${conversationId}/branches/${branch.id}`);
      scheduleNewBranchTitleRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the branch");
    } finally {
      setSending(false);
    }
  }

  async function resolveSuggestion(
    suggestion: BranchSuggestion,
    action: "accept" | "continue" | "dismiss",
  ) {
    setSending(true);
    setError("");
    try {
      if (action === "dismiss") {
        await api.dismissBranchSuggestion(conversationId, suggestion.id);
      } else {
        const result =
          action === "accept"
            ? await api.acceptBranchSuggestion(conversationId, suggestion.id)
            : await api.continueBranchSuggestion(conversationId, suggestion.id);
        applyChatResult(result);
      }
      setSuggestions((current) =>
        current.filter((item) => item.id !== suggestion.id),
      );
      await refreshBranchState();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not resolve the branch suggestion",
      );
    } finally {
      setSending(false);
    }
  }

  function handleComposerKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  if (loading && !conversation) {
    return <div className="page-state">Loading conversation…</div>;
  }

  return (
    <div className="conversation-page">
      {conversation && (
        <>
          <header className="conversation-header">
            <div>
              <Link
                className="back-link"
                to={project ? `/projects/${project.id}` : "/conversations?scope=standalone"}
              >
                ← {project?.name ?? "Standalone chats"}
              </Link>
              <h1>{conversation.title}</h1>
              <p>
                {workflowNames.length
                  ? `Context: ${workflowNames.join(" + ")}`
                  : "No workflow context"}
              </p>
            </div>
            <div className="conversation-header-actions">
              <ConversationActions
                conversation={conversation}
                onDeleted={() => navigate("/conversations", { replace: true })}
                onUpdated={setConversation}
              />
              <button
                className="secondary-button"
                onClick={() => setContextOpen((current) => !current)}
                type="button"
              >
                {contextOpen ? "Close workflows" : "Manage workflows"}
              </button>
              <span className="milestone-badge">
                {branches.length} branch{branches.length === 1 ? "" : "es"}
              </span>
            </div>
          </header>

          {error && <div className="conversation-error error-banner">{error}</div>}

          {contextOpen && (
            <section className="conversation-workflow-manager">
              <div>
                <p className="eyebrow">Conversation context</p>
                <h2>Reusable workflows</h2>
                <p>
                  Changes affect future Gemini replies. Stored messages remain unchanged.
                </p>
              </div>
              <div className="conversation-workflow-groups">
                {project && conversation && (
                  <label className="conversation-inheritance-toggle">
                    <input
                      checked={conversation.inherit_project_workflows}
                      disabled={sending}
                      onChange={(event) =>
                        setProjectWorkflowInheritance(event.target.checked)
                      }
                      type="checkbox"
                    />
                    <span>Use workflows attached to {project.name}</span>
                  </label>
                )}
                {!!inheritedWorkflows.length && (
                  <div>
                    <strong>Inherited from project</strong>
                    <div className="topic-chips">
                      {inheritedWorkflows.map((workflow) => (
                        <span key={workflow.id}>{workflow.name}</span>
                      ))}
                    </div>
                  </div>
                )}
                <div>
                  <strong>Attached directly</strong>
                  <div className="conversation-workflow-list">
                    {directWorkflows.map((workflow) => (
                      <span className="removable-chip" key={workflow.id}>
                        {workflow.name}
                        <button
                          aria-label={`Detach ${workflow.name}`}
                          disabled={sending}
                          onClick={() => detachConversationWorkflow(workflow)}
                          type="button"
                        >
                          ×
                        </button>
                      </span>
                    ))}
                    {!directWorkflows.length && <small>None attached directly.</small>}
                  </div>
                </div>
                {!!availableDirectWorkflows.length && (
                  <form
                    className="conversation-workflow-attach"
                    onSubmit={attachConversationWorkflow}
                  >
                    <label>
                      Add from library
                      <select
                        onChange={(event) => setWorkflowToAttach(event.target.value)}
                        value={workflowToAttach}
                      >
                        {availableDirectWorkflows.map((workflow) => (
                          <option key={workflow.id} value={workflow.id}>
                            {workflow.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <button className="secondary-button" disabled={sending}>
                      Attach
                    </button>
                  </form>
                )}
              </div>
            </section>
          )}

          <div className="conversation-layout">
            <aside className="tree-panel">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Navigation</p>
                  <h2>Branches</h2>
                </div>
                <span className="count-badge">{branches.length}</span>
              </div>
              <ConversationBranches
                branches={branches}
                selectedId={branchId ?? null}
                onSelect={(selectedBranchId) =>
                  navigate(
                    `/conversations/${conversationId}/branches/${selectedBranchId}`,
                  )
                }
              />
            </aside>

            <section className="chat-panel">
              <div className="chat-content">
                {visibleSuggestion && (
                  <section className="branch-suggestion" role="status">
                    <div className="suggestion-mark">⑂</div>
                    <div className="suggestion-copy">
                      <p className="eyebrow">Gemini suggests a branch</p>
                      <h2>This may be a useful side path.</h2>
                      <p>{visibleSuggestion.reason}</p>
                      {!!visibleSuggestion.referenced_topics?.length && (
                        <div className="topic-chips">
                          {visibleSuggestion.referenced_topics.map((topic) => (
                            <span key={topic}>{topic}</span>
                          ))}
                        </div>
                      )}
                      <small>
                        {Math.round(visibleSuggestion.confidence * 100)}% confidence ·
                        your main trunk stays unchanged
                      </small>
                    </div>
                    <div className="suggestion-actions">
                      <button
                        className="primary-button"
                        disabled={sending}
                        onClick={() => resolveSuggestion(visibleSuggestion, "accept")}
                        type="button"
                      >
                        Start branch
                      </button>
                      <button
                        className="secondary-button"
                        disabled={sending}
                        onClick={() => resolveSuggestion(visibleSuggestion, "continue")}
                        type="button"
                      >
                        Continue here
                      </button>
                      <button
                        className="text-button"
                        disabled={sending}
                        onClick={() => resolveSuggestion(visibleSuggestion, "dismiss")}
                        type="button"
                      >
                        Dismiss
                      </button>
                    </div>
                  </section>
                )}

                {activeBranch && (
                  <section className="branch-context-card">
                    <div className="branch-context-heading">
                      <div>
                        <p className="eyebrow">Active context</p>
                        <h2>{activeBranch.name}</h2>
                      </div>
                      <span className={`summary-status ${activeBranch.summary_status}`}>
                        {activeBranch.summary_status === "pending"
                          ? "Ready to prompt"
                          : activeBranch.summary_status === "failed"
                            ? "Summary unavailable"
                            : "Current"}
                      </span>
                    </div>
                    <p>
                      {activeBranch.is_main
                        ? "The main trunk uses its complete message history."
                        : activeBranch.context_summary ||
                          (activeBranch.summary_status === "pending"
                            ? "Earlier chat history is stored privately. Gemini will focus it when you send your first prompt here."
                            : activeBranch.summary_status === "failed"
                              ? "The context snapshot could not be created."
                              : "Gemini found no earlier context relevant to this branch.")}
                    </p>
                    {!activeBranch.is_main &&
                      activeBranch.summary_status === "ready" && (
                        <p className="context-explanation">
                          Earlier messages remain saved. “Leaving out” shows source
                          topics excluded from Gemini’s active snapshot for this branch.
                        </p>
                      )}
                    {!!activeBranch.retained_topics?.length && (
                      <div className="context-topic-row">
                        <strong>Retaining</strong>
                        <div className="topic-chips">
                          {activeBranch.retained_topics.map((topic) => (
                            <span key={topic}>{topic}</span>
                          ))}
                        </div>
                      </div>
                    )}
                    {!!activeBranch.omitted_topics?.length && (
                      <div className="context-topic-editor">
                        <div className="context-topic-row omitted">
                          <strong>Leaving out</strong>
                          <div className="topic-chips selectable-topic-chips">
                            {activeBranch.omitted_topics.map((topic) => (
                              <button
                                aria-pressed={selectedContextTopics.includes(topic)}
                                disabled={expandingContext}
                                key={topic}
                                onClick={() => toggleContextTopic(topic)}
                                type="button"
                              >
                                {selectedContextTopics.includes(topic) ? "✓ " : "+ "}
                                {topic}
                              </button>
                            ))}
                          </div>
                        </div>
                        <button
                          className="secondary-button context-include-button"
                          disabled={!selectedContextTopics.length || expandingContext}
                          onClick={includeSelectedContext}
                          type="button"
                        >
                          {expandingContext
                            ? "Adding context…"
                            : `Include selected${
                                selectedContextTopics.length
                                  ? ` (${selectedContextTopics.length})`
                                  : ""
                              }`}
                        </button>
                      </div>
                    )}
                  </section>
                )}

                {!messages.length && !pendingUserMessage && activeBranch && (
                  <div className="chat-empty compact-chat-empty">
                    <span className="chat-empty-mark">✦</span>
                    <h2>Start the main trunk.</h2>
                    <p>
                      Send the first message below. You can start a branch from any
                      saved Gemini answer as the chat grows.
                    </p>
                  </div>
                )}

                <div className="message-path">
                  {messages.map((message) => {
                    const duration = messageGenerationDuration(message);
                    return (
                      <article className={`message ${message.role}`} key={message.id}>
                        <div className="message-heading">
                          <span>{message.role === "assistant" ? "Gemini" : "You"}</span>
                          {message.role === "assistant" && (
                            <div className="message-heading-actions">
                              {duration !== null && (
                                <small className="message-duration">
                                  Generated in {formatDuration(duration)}
                                </small>
                              )}
                              <button
                                className="message-action"
                                disabled={sending}
                                onClick={() => createBranchFromAnswer(message)}
                                type="button"
                              >
                                Start branch
                              </button>
                            </div>
                          )}
                        </div>
                        <MarkdownContent content={message.content} />
                      </article>
                    );
                  })}
                  {pendingUserMessage && (
                    <article className="message user pending-user-message">
                      <div className="message-heading">
                        <span>You</span>
                      </div>
                      <MarkdownContent content={pendingUserMessage} />
                    </article>
                  )}
                  {generationStartedAt !== null && (
                    <article
                      aria-live="polite"
                      className="message assistant generating-message"
                      ref={pendingAnswerRef}
                      role="status"
                    >
                      <div className="message-heading">
                        <span>Gemini</span>
                      </div>
                      <div className="generation-status">
                        <span aria-hidden="true" className="thinking-dots">
                          <i />
                          <i />
                          <i />
                        </span>
                        <span>Generating</span>
                        <time>{formatDuration(generationElapsedMs)}</time>
                      </div>
                    </article>
                  )}
                </div>
              </div>

              <form className="chat-composer" onSubmit={sendMessage}>
                <label htmlFor="chat-message">
                  Continue {activeBranch?.name ?? "this chat"}
                </label>
                <div className="composer-row">
                  <textarea
                    disabled={activeBranchHasPendingSuggestion}
                    id="chat-message"
                    onChange={(event) => setComposer(event.target.value)}
                    onKeyDown={handleComposerKeyDown}
                    placeholder={
                      activeBranchHasPendingSuggestion
                        ? "Resolve Gemini’s branch suggestion above to continue"
                        : "Ask Gemini… (Shift + Enter for a new line)"
                    }
                    rows={3}
                    value={composer}
                  />
                  <button
                    className="primary-button send-button"
                    disabled={
                      sending ||
                      !composer.trim() ||
                      !activeBranch ||
                      activeBranchHasPendingSuggestion
                    }
                  >
                    {generationStartedAt !== null ? (
                      <span className="send-progress">
                        <span aria-hidden="true" className="button-spinner" />
                        {formatDuration(generationElapsedMs)}
                      </span>
                    ) : (
                      "Send"
                    )}
                  </button>
                </div>
              </form>
            </section>
          </div>
        </>
      )}

    </div>
  );
}
