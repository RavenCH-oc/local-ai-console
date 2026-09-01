export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
}

export interface VersionResponse {
  application: string;
  service: string;
  version: string;
}

export interface RuntimeLayoutResponse {
  config: string;
  data: string;
  prompts: string;
  knowledge: string;
  logs: string;
  cache: string;
  backups: string;
}

export interface RuntimeInfoResponse {
  root: string;
  source: "environment_override" | "windows_default";
  initialized: boolean;
  paths: RuntimeLayoutResponse;
}

export type LlmRuntimeSlotState = "unconfigured" | "unavailable" | "checking" | "loading" | "ready" | "error";

export interface LlmRuntimeSlotStatus {
  configured: boolean;
  state: LlmRuntimeSlotState;
  provider: string | null;
  expected_model_alias_configured: boolean;
  error_code: string | null;
}

export interface LlmRuntimeStatus {
  main: LlmRuntimeSlotStatus;
  utility: LlmRuntimeSlotStatus;
}

export type PromptProjectStatus = "active" | "archived";
export type PromptSessionStatus = "active" | "closed";
export type PromptMessageRole = "user" | "assistant" | "system" | "tool";
export type PromptRevisionStatus = "proposed" | "accepted" | "discarded";
export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export interface PromptProject {
  id: string;
  title: string;
  workflow_profile_id: string;
  created_at: string;
  updated_at: string;
  active_session_id: string | null;
  current_revision_id: string | null;
  status: PromptProjectStatus;
  archived_at: string | null;
}

export interface PromptSession {
  id: string;
  project_id: string;
  title: string | null;
  status: PromptSessionStatus;
  created_at: string;
  updated_at: string;
}

export interface PromptMessage {
  id: string;
  session_id: string;
  role: PromptMessageRole;
  content: string;
  metadata: Record<string, JsonValue> | null;
  created_at: string;
}

export interface PromptProjectState {
  id: string;
  project_id: string;
  objective: string;
  important_constraints: string[];
  must_preserve: string[];
  known_problems: string[];
  accepted_observations: string[];
  updated_at: string;
}

export interface PromptRevision {
  id: string;
  project_id: string;
  parent_revision_id: string | null;
  positive_prompt: string;
  negative_prompt: string;
  parameters: Record<string, JsonValue>;
  change_log: string;
  status: PromptRevisionStatus;
  created_at: string;
}

export interface CreatePromptProjectInput {
  title: string;
  workflow_profile_id?: string;
}

export interface UpdatePromptProjectStateInput {
  objective: string;
  important_constraints: string[];
  must_preserve: string[];
  known_problems: string[];
  accepted_observations: string[];
}

export interface CreatePromptRevisionInput {
  parent_revision_id: string | null;
  positive_prompt: string;
  negative_prompt: string;
  parameters: Record<string, JsonValue>;
  change_log: string;
}

export class ControlApiRequestError extends Error {
  constructor() {
    super("The Controller API request did not succeed.");
    this.name = "ControlApiRequestError";
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT";
  body?: unknown;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`/api${path}`, {
      method: options.method ?? "GET",
      headers: {
        Accept: "application/json",
        ...(options.body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    throw new ControlApiRequestError();
  }

  if (!response.ok) {
    throw new ControlApiRequestError();
  }

  return (await response.json()) as T;
}

export const controlApi = {
  health: (): Promise<HealthResponse> => request<HealthResponse>("/health"),
  version: (): Promise<VersionResponse> => request<VersionResponse>("/version"),
  runtimeInfo: (): Promise<RuntimeInfoResponse> => request<RuntimeInfoResponse>("/runtime/info"),
  getLlmRuntimeStatus: (): Promise<LlmRuntimeStatus> => request<LlmRuntimeStatus>("/llm/status"),
  probeLlmRuntimes: (): Promise<LlmRuntimeStatus> => request<LlmRuntimeStatus>("/llm/probe", { method: "POST" }),
  listPromptProjects: (): Promise<PromptProject[]> => request<PromptProject[]>("/prompt-projects"),
  createPromptProject: (input: CreatePromptProjectInput): Promise<PromptProject> =>
    request<PromptProject>("/prompt-projects", { method: "POST", body: input }),
  getPromptProject: (projectId: string): Promise<PromptProject> =>
    request<PromptProject>(`/prompt-projects/${projectId}`),
  renamePromptProject: (projectId: string, title: string): Promise<PromptProject> =>
    request<PromptProject>(`/prompt-projects/${projectId}`, { method: "PATCH", body: { title } }),
  archivePromptProject: (projectId: string): Promise<PromptProject> =>
    request<PromptProject>(`/prompt-projects/${projectId}/archive`, { method: "POST" }),
  listPromptSessions: (projectId: string): Promise<PromptSession[]> =>
    request<PromptSession[]>(`/prompt-projects/${projectId}/sessions`),
  createPromptSession: (projectId: string, title?: string): Promise<PromptSession> =>
    request<PromptSession>(`/prompt-projects/${projectId}/sessions`, { method: "POST", body: { title } }),
  listPromptMessages: (sessionId: string): Promise<PromptMessage[]> =>
    request<PromptMessage[]>(`/prompt-sessions/${sessionId}/messages`),
  appendPromptMessage: (sessionId: string, content: string): Promise<PromptMessage> =>
    request<PromptMessage>(`/prompt-sessions/${sessionId}/messages`, {
      method: "POST",
      body: { role: "user", content },
    }),
  getPromptProjectState: (projectId: string): Promise<PromptProjectState> =>
    request<PromptProjectState>(`/prompt-projects/${projectId}/state`),
  updatePromptProjectState: (
    projectId: string,
    input: UpdatePromptProjectStateInput,
  ): Promise<PromptProjectState> =>
    request<PromptProjectState>(`/prompt-projects/${projectId}/state`, { method: "PUT", body: input }),
  listPromptRevisions: (projectId: string): Promise<PromptRevision[]> =>
    request<PromptRevision[]>(`/prompt-projects/${projectId}/revisions`),
  createPromptRevision: (projectId: string, input: CreatePromptRevisionInput): Promise<PromptRevision> =>
    request<PromptRevision>(`/prompt-projects/${projectId}/revisions`, { method: "POST", body: input }),
  acceptPromptRevision: (revisionId: string): Promise<PromptRevision> =>
    request<PromptRevision>(`/prompt-revisions/${revisionId}/accept`, { method: "POST" }),
  discardPromptRevision: (revisionId: string): Promise<PromptRevision> =>
    request<PromptRevision>(`/prompt-revisions/${revisionId}/discard`, { method: "POST" }),
};
