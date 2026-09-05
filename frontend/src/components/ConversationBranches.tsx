import type { ConversationBranch } from "../types";

interface BranchNode extends ConversationBranch {
  children: BranchNode[];
}

function buildBranchTree(branches: ConversationBranch[]): BranchNode[] {
  const nodes = new Map<string, BranchNode>();
  branches.forEach((branch) => nodes.set(branch.id, { ...branch, children: [] }));

  const roots: BranchNode[] = [];
  nodes.forEach((node) => {
    const parent = node.parent_branch_id
      ? nodes.get(node.parent_branch_id)
      : undefined;
    if (parent && parent.id !== node.id) parent.children.push(node);
    else roots.push(node);
  });

  const sortNodes = (items: BranchNode[]) => {
    items.sort((left, right) => {
      if (left.is_main !== right.is_main) return left.is_main ? -1 : 1;
      return left.created_at.localeCompare(right.created_at);
    });
    items.forEach((item) => sortNodes(item.children));
  };
  sortNodes(roots);
  return roots;
}

function ancestorIds(branches: ConversationBranch[], selectedId: string | null) {
  const byId = new Map(branches.map((branch) => [branch.id, branch]));
  const ids = new Set<string>();
  const visited = new Set<string>();
  let current = selectedId ? byId.get(selectedId) : undefined;
  while (current && !visited.has(current.id)) {
    visited.add(current.id);
    ids.add(current.id);
    current = current.parent_branch_id
      ? byId.get(current.parent_branch_id)
      : undefined;
  }
  return ids;
}

interface ConversationBranchesProps {
  branches: ConversationBranch[];
  selectedId: string | null;
  onSelect: (branchId: string) => void;
}

export function ConversationBranches({
  branches,
  selectedId,
  onSelect,
}: ConversationBranchesProps) {
  const roots = buildBranchTree(branches);
  const activePath = ancestorIds(branches, selectedId);

  if (!roots.length) {
    return (
      <div className="tree-empty branch-tree-empty">
        <span className="tree-empty-icon">⑂</span>
        <strong>Your branches will appear here</strong>
        <p>The main trunk is created when the chat is ready for its first message.</p>
      </div>
    );
  }

  const renderNode = (node: BranchNode) => {
    const selected = node.id === selectedId;
    const onPath = activePath.has(node.id);
    return (
      <li key={node.id}>
        <button
          aria-current={selected ? "page" : undefined}
          className={`branch-node${selected ? " selected" : ""}${
            onPath && !selected ? " ancestor" : ""
          }`}
          onClick={() => onSelect(node.id)}
          type="button"
        >
          <span className="branch-node-heading">
            <strong>{node.name}</strong>
            {node.is_main && <small>Main</small>}
          </span>
          <span className="branch-summary-preview">
            {node.is_main
              ? "Full conversation history."
              : node.context_summary ||
              (node.summary_status === "pending"
                ? "Waiting for the first branch prompt."
                : node.summary_status === "failed"
                  ? "Context summary unavailable."
                  : "No earlier context was relevant.")}
          </span>
          {!!node.retained_topics?.length && (
            <span className="branch-topic-count">
              {node.retained_topics.length} retained topic
              {node.retained_topics.length === 1 ? "" : "s"}
            </span>
          )}
        </button>
        {node.children.length > 0 && <ul>{node.children.map(renderNode)}</ul>}
      </li>
    );
  };

  return <ul className="branch-tree">{roots.map(renderNode)}</ul>;
}
