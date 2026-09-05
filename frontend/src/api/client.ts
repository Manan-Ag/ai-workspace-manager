import type {
  BranchInput,
  BranchSuggestion,
  ChatTurnResponse,
  Conversation,
  ConversationBranch,
  ConversationInput,
  Message,
  Project,
  ProjectInput,
  Workflow,
  WorkflowInput,
} from "../types";

const API_URL = (
  import.meta.env.VITE_API_URL ??
  (import.meta.env.PROD ? "" : "http://localhost:8000")
).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function errorDetail(body: unknown): string | null {
  if (!body || typeof body !== "object" || !("detail" in body)) return null;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first = detail[0];
    if (first && typeof first === "object" && "msg" in first) {
      return String((first as { msg: unknown }).msg);
    }
  }
  return null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    let message = "Something went wrong. Please try again.";
    try {
      message = errorDetail(await response.json()) ?? message;
    } catch {
      // Keep the safe fallback instead of exposing a raw server response.
    }
    throw new ApiError(message, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function queryString(values: Record<string, string | boolean | undefined>) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined) params.set(key, String(value));
  });
  const value = params.toString();
  return value ? `?${value}` : "";
}

export const api = {
  listProjects: () => request<Project[]>("/api/projects"),
  getProject: (projectId: string) =>
    request<Project>(`/api/projects/${projectId}`),
  createProject: (input: ProjectInput) =>
    request<Project>("/api/projects", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  updateProject: (projectId: string, input: Partial<ProjectInput>) =>
    request<Project>(`/api/projects/${projectId}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    }),

  listWorkflows: () => request<Workflow[]>("/api/workflows"),
  listProjectWorkflows: (projectId: string) =>
    request<Workflow[]>(`/api/projects/${projectId}/workflows`),
  getWorkflow: (workflowId: string) =>
    request<Workflow>(`/api/workflows/${workflowId}`),
  createWorkflow: (input: WorkflowInput) =>
    request<Workflow>("/api/workflows", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  updateWorkflow: (workflowId: string, input: Partial<WorkflowInput>) =>
    request<Workflow>(`/api/workflows/${workflowId}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    }),
  attachWorkflowToProject: (
    projectId: string,
    workflowId: string,
    position?: number,
  ) =>
    request<void>(`/api/projects/${projectId}/workflows/${workflowId}`, {
      method: "PUT",
      body: JSON.stringify(position === undefined ? {} : { position }),
    }),
  detachWorkflowFromProject: (projectId: string, workflowId: string) =>
    request<void>(`/api/projects/${projectId}/workflows/${workflowId}`, {
      method: "DELETE",
    }),

  listConversations: (filters?: {
    projectId?: string;
    standalone?: boolean;
    search?: string;
  }) =>
    request<Conversation[]>(
      `/api/conversations${queryString({
        project_id: filters?.projectId,
        standalone: filters?.standalone,
        q: filters?.search,
      })}`,
    ),
  getConversation: (conversationId: string) =>
    request<Conversation>(`/api/conversations/${conversationId}`),
  createConversation: (input: ConversationInput) =>
    request<Conversation>("/api/conversations", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  updateConversation: (
    conversationId: string,
    input: Partial<ConversationInput>,
  ) =>
    request<Conversation>(`/api/conversations/${conversationId}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    }),
  deleteConversation: (conversationId: string) =>
    request<void>(`/api/conversations/${conversationId}`, {
      method: "DELETE",
    }),
  attachWorkflowToConversation: (
    conversationId: string,
    workflowId: string,
    position?: number,
  ) =>
    request<Workflow>(
      `/api/conversations/${conversationId}/workflows/${workflowId}`,
      {
        method: "PUT",
        body: JSON.stringify(position === undefined ? {} : { position }),
      },
    ),
  detachWorkflowFromConversation: (
    conversationId: string,
    workflowId: string,
  ) =>
    request<void>(
      `/api/conversations/${conversationId}/workflows/${workflowId}`,
      { method: "DELETE" },
    ),

  listBranches: (conversationId: string) =>
    request<ConversationBranch[]>(
      `/api/conversations/${conversationId}/branches`,
    ),
  listBranchMessages: (conversationId: string, branchId: string) =>
    request<Message[]>(
      `/api/conversations/${conversationId}/branches/${branchId}/messages`,
    ),
  includeBranchContext: (
    conversationId: string,
    branchId: string,
    topics: string[],
  ) =>
    request<ConversationBranch>(
      `/api/conversations/${conversationId}/branches/${branchId}/context/include`,
      {
        method: "POST",
        body: JSON.stringify({ topics }),
      },
    ),
  createBranch: (conversationId: string, input: BranchInput) =>
    request<ConversationBranch>(`/api/conversations/${conversationId}/branches`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  sendBranchMessage: (
    conversationId: string,
    branchId: string,
    content: string,
    expectedHeadMessageId?: string | null,
  ) =>
    request<ChatTurnResponse>(
      `/api/conversations/${conversationId}/branches/${branchId}/messages`,
      {
        method: "POST",
        body: JSON.stringify({
          content,
          expected_head_message_id: expectedHeadMessageId,
        }),
      },
    ),

  listBranchSuggestions: (conversationId: string) =>
    request<BranchSuggestion[]>(
      `/api/conversations/${conversationId}/branch-suggestions?status=pending`,
    ),
  acceptBranchSuggestion: (conversationId: string, suggestionId: string) =>
    request<ChatTurnResponse>(
      `/api/conversations/${conversationId}/branch-suggestions/${suggestionId}/accept`,
      { method: "POST" },
    ),
  continueBranchSuggestion: (conversationId: string, suggestionId: string) =>
    request<ChatTurnResponse>(
      `/api/conversations/${conversationId}/branch-suggestions/${suggestionId}/continue`,
      { method: "POST" },
    ),
  dismissBranchSuggestion: (conversationId: string, suggestionId: string) =>
    request<void>(
      `/api/conversations/${conversationId}/branch-suggestions/${suggestionId}/dismiss`,
      { method: "POST" },
    ),
};
