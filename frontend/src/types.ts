export interface Project {
  id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
}

export interface Workflow {
  id: string;
  name: string;
  description: string;
  system_prompt: string;
  prompt_template: string;
  model_name: string | null;
  temperature: number;
  created_at: string;
  updated_at: string;
}

export interface Conversation {
  id: string;
  project_id: string | null;
  title: string;
  workflow_ids: string[];
  effective_workflow_ids: string[];
  model_name: string | null;
  temperature: number;
  inherit_project_workflows: boolean;
  main_branch_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  parent_message_id: string | null;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
  metadata: Record<string, unknown>;
}

export type BranchSummaryStatus =
  | "not_required"
  | "pending"
  | "ready"
  | "failed";

export interface ConversationBranch {
  id: string;
  conversation_id: string;
  parent_branch_id: string | null;
  forked_from_message_id: string | null;
  head_message_id: string | null;
  name: string;
  is_main: boolean;
  context_summary: string | null;
  retained_topics: string[];
  omitted_topics: string[];
  summary_status: BranchSummaryStatus;
  created_at: string;
  updated_at: string;
}

export type BranchSuggestionStatus =
  | "pending"
  | "accepted"
  | "continued"
  | "dismissed";

export interface BranchSuggestion {
  id: string;
  conversation_id: string;
  source_leaf_message_id: string;
  created_branch_id: string | null;
  reason: string;
  referenced_topics: string[];
  confidence: number;
  status: BranchSuggestionStatus;
  suggested_anchor_message_id: string;
  source_branch_id: string;
  user_content: string;
  created_at: string;
  updated_at: string;
}

export interface CompletedChatTurn {
  kind: "completed";
  branch: ConversationBranch;
  user_message: Message;
  assistant_message: Message;
}

export interface SuggestedChatTurn {
  kind: "branch_suggested";
  branch: ConversationBranch;
  suggestion: BranchSuggestion;
}

export type ChatTurnResponse = CompletedChatTurn | SuggestedChatTurn;

export interface ProjectInput {
  name: string;
  description: string;
}

export interface WorkflowInput {
  name: string;
  description: string;
  system_prompt: string;
  prompt_template: string;
  model_name: string | null;
  temperature: number;
}

export interface ConversationInput {
  title: string | null;
  project_id: string | null;
  workflow_ids: string[];
  model_name?: string | null;
  temperature?: number;
  inherit_project_workflows: boolean;
}

export interface BranchInput {
  source_branch_id: string;
  forked_from_message_id: string;
  name: string;
}
