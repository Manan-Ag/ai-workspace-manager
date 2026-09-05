import { FormEvent, useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { api } from "../api/client";
import type { Conversation } from "../types";

interface ConversationActionsProps {
  conversation: Conversation;
  onDeleted: (conversation: Conversation) => void;
  onMenuOpenChange?: (open: boolean) => void;
  onUpdated: (conversation: Conversation) => void;
}

export function ConversationActions({
  conversation,
  onDeleted,
  onMenuOpenChange,
  onUpdated,
}: ConversationActionsProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [dialog, setDialog] = useState<"rename" | "delete" | null>(null);
  const [title, setTitle] = useState(conversation.title);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setTitle(conversation.title);
  }, [conversation.title]);

  function openDialog(nextDialog: "rename" | "delete") {
    setMenuOpen(false);
    onMenuOpenChange?.(false);
    setError("");
    setTitle(conversation.title);
    setDialog(nextDialog);
  }

  function closeDialog() {
    if (saving) return;
    setDialog(null);
    setError("");
  }

  async function renameConversation(event: FormEvent) {
    event.preventDefault();
    const nextTitle = title.trim();
    if (!nextTitle || nextTitle === conversation.title) {
      closeDialog();
      return;
    }
    setSaving(true);
    setError("");
    try {
      const updated = await api.updateConversation(conversation.id, {
        title: nextTitle,
      });
      onUpdated(updated);
      window.dispatchEvent(new Event("conversations-updated"));
      setDialog(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not rename the chat");
    } finally {
      setSaving(false);
    }
  }

  async function deleteConversation() {
    setSaving(true);
    setError("");
    try {
      await api.deleteConversation(conversation.id);
      onDeleted(conversation);
      window.dispatchEvent(new Event("conversations-updated"));
      setDialog(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete the chat");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="conversation-actions">
        <button
          aria-expanded={menuOpen}
          aria-haspopup="menu"
          aria-label={`Actions for ${conversation.title}`}
          className="conversation-menu-trigger"
          onClick={() =>
            setMenuOpen((current) => {
              onMenuOpenChange?.(!current);
              return !current;
            })
          }
          type="button"
        >
          <span aria-hidden="true">•••</span>
        </button>
        {menuOpen && (
          <div className="conversation-action-menu" role="menu">
            <button onClick={() => openDialog("rename")} role="menuitem" type="button">
              Rename
            </button>
            <button
              className="danger-text"
              onClick={() => openDialog("delete")}
              role="menuitem"
              type="button"
            >
              Delete
            </button>
          </div>
        )}
      </div>

      {dialog &&
        createPortal(
          <div
            className="modal-backdrop"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) closeDialog();
            }}
          >
            <section
              aria-labelledby="conversation-dialog-title"
              aria-modal="true"
              className="modal-card conversation-action-dialog"
              role="dialog"
            >
              {dialog === "rename" ? (
                <form onSubmit={renameConversation}>
                  <p className="eyebrow accent">Chat settings</p>
                  <h2 id="conversation-dialog-title">Rename chat</h2>
                  <label htmlFor={`rename-chat-${conversation.id}`}>Chat title</label>
                  <input
                    autoFocus
                    id={`rename-chat-${conversation.id}`}
                    maxLength={200}
                    onChange={(event) => setTitle(event.target.value)}
                    value={title}
                  />
                  {error && <div className="inline-dialog-error">{error}</div>}
                  <div className="dialog-actions">
                    <button
                      className="secondary-button"
                      disabled={saving}
                      onClick={closeDialog}
                      type="button"
                    >
                      Cancel
                    </button>
                    <button
                      className="primary-button"
                      disabled={saving || !title.trim()}
                    >
                      {saving ? "Saving…" : "Save name"}
                    </button>
                  </div>
                </form>
              ) : (
                <div>
                  <p className="eyebrow danger-eyebrow">Permanent action</p>
                  <h2 id="conversation-dialog-title">Delete this chat?</h2>
                  <p>
                    “{conversation.title}” and all of its messages and branches will
                    be permanently deleted. This cannot be undone.
                  </p>
                  {error && <div className="inline-dialog-error">{error}</div>}
                  <div className="dialog-actions">
                    <button
                      className="secondary-button"
                      disabled={saving}
                      onClick={closeDialog}
                      type="button"
                    >
                      Cancel
                    </button>
                    <button
                      className="primary-button destructive-button"
                      disabled={saving}
                      onClick={deleteConversation}
                      type="button"
                    >
                      {saving ? "Deleting…" : "Delete chat"}
                    </button>
                  </div>
                </div>
              )}
            </section>
          </div>,
          document.body,
        )}
    </>
  );
}
