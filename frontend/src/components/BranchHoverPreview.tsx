import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { ConversationBranch } from "../types";

interface BranchHoverPreviewProps {
  conversationId: string;
  mainBranchId: string | null;
  visible: boolean;
}

export function BranchHoverPreview({
  conversationId,
  mainBranchId,
  visible,
}: BranchHoverPreviewProps) {
  const [branches, setBranches] = useState<ConversationBranch[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!visible || branches !== null || failed) return;
    let cancelled = false;
    api
      .listBranches(conversationId)
      .then((items) => {
        if (!cancelled) setBranches(items);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [branches, conversationId, failed, visible]);

  const firstTier = useMemo(
    () =>
      (branches ?? []).filter(
        (branch) => !branch.is_main && branch.parent_branch_id === mainBranchId,
      ),
    [branches, mainBranchId],
  );

  if (!visible) return null;

  return (
    <div className="branch-hover-preview">
      <strong>Branches from Main</strong>
      {branches === null && !failed && <span>Loading branches…</span>}
      {failed && <span>Branches unavailable</span>}
      {branches !== null && !firstTier.length && <span>No branches yet</span>}
      {firstTier.map((branch) => (
        <Link
          key={branch.id}
          to={`/conversations/${conversationId}/branches/${branch.id}`}
        >
          <span className="nav-dot" />
          <span>{branch.name}</span>
        </Link>
      ))}
    </div>
  );
}
