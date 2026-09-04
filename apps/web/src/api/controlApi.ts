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
export type PromptWorkflowMode = "stable" | "balanced" | "detailed" | "preserve";
export type PromptDiscussionThinkingMode = "auto" | "off" | "on";
export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export interface PromptProject {
  id: string;
  title: string;
  workflow_profile_id: string;
  workflow_mode: PromptWorkflowMode;
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
  workflow_mode?: PromptWorkflowMode;
}

export interface PromptWorkflowKnowledgeSource {
  id: string;
  label: string;
  source_kind: "built_in" | "private_runtime";
  stability: "stable" | "snapshot" | "append_only" | "dynamic";
}

export interface PromptWorkflow {
  id: string;
  display_name: string;
  model_family: string;
  supported_modes: PromptWorkflowMode[];
  default_mode: PromptWorkflowMode;
  knowledge_sources: PromptWorkflowKnowledgeSource[];
}

export interface PromptContextContributionPreview {
  label: string;
  kind: string;
  source: string;
  stability: "stable" | "snapshot" | "append_only" | "dynamic";
  character_count: number;
  token_count: number | null;
}

export interface PromptContextPreview {
  workflow_profile_id: string;
  workflow_mode: PromptWorkflowMode;
  contributions: PromptContextContributionPreview[];
}

export interface PromptDiscussionStreamCallbacks {
  started: (event: { user_message_id: string; input_tokens: number; max_output_tokens: number }) => void;
  reasoningDelta: (text: string) => void;
  textDelta: (text: string) => void;
  completed: (event: { assistant_message_id: string; finish_reason: string; input_tokens: number }) => void;
  cancelled: () => void;
  error: (event: { code: string; message: string }) => void;
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
  constructor(message = "The Controller API request did not succeed.") {
    super(message);
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
    throw await responseError(response);
  }

  return (await response.json()) as T;
}

async function responseError(response: Response): Promise<ControlApiRequestError> {
  try {
    const payload: unknown = await response.json();
    if (
      payload !== null &&
      typeof payload === "object" &&
      "detail" in payload &&
      typeof payload.detail === "string" &&
      payload.detail.trim()
    ) {
      return new ControlApiRequestError(payload.detail);
    }
  } catch {
    // A non-JSON error must still stay generic at the browser boundary.
  }
  return new ControlApiRequestError();
}

function parseDiscussionEvent(block: string): { event: string; data: Record<string, unknown> } {
  let event = "";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trim());
    }
  }
  if (!event || dataLines.length === 0) {
    throw new ControlApiRequestError("Prompt discussion stream data was invalid.");
  }
  try {
    const parsed: unknown = JSON.parse(dataLines.join("\n"));
    if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) {
      return { event, data: parsed as Record<string, unknown> };
    }
  } catch {
    // Use the same safe error for malformed controller events.
  }
  throw new ControlApiRequestError("Prompt discussion stream data was invalid.");
}

function requiredString(data: Record<string, unknown>, name: string): string {
  const value = data[name];
  if (typeof value !== "string" || !value) {
    throw new ControlApiRequestError("Prompt discussion stream data was invalid.");
  }
  return value;
}

function requiredNumber(data: Record<string, unknown>, name: string): number {
  const value = data[name];
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new ControlApiRequestError("Prompt discussion stream data was invalid.");
  }
  return value;
}

function dispatchDiscussionEvent(
  event: string,
  data: Record<string, unknown>,
  callbacks: PromptDiscussionStreamCallbacks,
): void {
  if (event === "started") {
    callbacks.started({
      user_message_id: requiredString(data, "user_message_id"),
      input_tokens: requiredNumber(data, "input_tokens"),
      max_output_tokens: requiredNumber(data, "max_output_tokens"),
    });
  } else if (event === "reasoning_delta") {
    callbacks.reasoningDelta(requiredString(data, "text"));
  } else if (event === "text_delta") {
    callbacks.textDelta(requiredString(data, "text"));
  } else if (event === "completed") {
    callbacks.completed({
      assistant_message_id: requiredString(data, "assistant_message_id"),
      finish_reason: requiredString(data, "finish_reason"),
      input_tokens: requiredNumber(data, "input_tokens"),
    });
  } else if (event === "cancelled") {
    callbacks.cancelled();
  } else if (event === "error") {
    callbacks.error({ code: requiredString(data, "code"), message: requiredString(data, "message") });
  } else {
    throw new ControlApiRequestError("Prompt discussion stream data was invalid.");
  }
}

async function streamPromptDiscussion(
  sessionId: string,
  input: { content: string; thinking_mode: PromptDiscussionThinkingMode },
  callbacks: PromptDiscussionStreamCallbacks,
  signal: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`/api/prompt-sessions/${sessionId}/discussion/stream`, {
      method: "POST",
      headers: { Accept: "text/event-stream", "Content-Type": "application/json" },
      body: JSON.stringify(input),
      signal,
    });
  } catch {
    if (signal.aborted) {
      return;
    }
    throw new ControlApiRequestError("The Prompt Workbench discussion stream could not be started.");
  }
  if (!response.ok) {
    throw await responseError(response);
  }
  if (!response.body) {
    throw new ControlApiRequestError("The Prompt Workbench discussion stream was unavailable.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const consume = () => {
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary).replace(/\r/g, "");
      buffer = buffer.slice(boundary + 2);
      if (block.trim()) {
        const parsed = parseDiscussionEvent(block);
        dispatchDiscussionEvent(parsed.event, parsed.data, callbacks);
      }
      boundary = buffer.indexOf("\n\n");
    }
  };
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      consume();
    }
    buffer += decoder.decode();
    consume();
    if (buffer.trim()) {
      throw new ControlApiRequestError("Prompt discussion stream data was incomplete.");
    }
  } finally {
    reader.releaseLock();
  }
}

export const controlApi = {
  health: (): Promise<HealthResponse> => request<HealthResponse>("/health"),
  version: (): Promise<VersionResponse> => request<VersionResponse>("/version"),
  runtimeInfo: (): Promise<RuntimeInfoResponse> => request<RuntimeInfoResponse>("/runtime/info"),
  getLlmRuntimeStatus: (): Promise<LlmRuntimeStatus> => request<LlmRuntimeStatus>("/llm/status"),
  probeLlmRuntimes: (): Promise<LlmRuntimeStatus> => request<LlmRuntimeStatus>("/llm/probe", { method: "POST" }),
  listPromptProjects: (): Promise<PromptProject[]> => request<PromptProject[]>("/prompt-projects"),
  listPromptWorkflows: (): Promise<PromptWorkflow[]> => request<PromptWorkflow[]>("/prompt-workflows"),
  createPromptProject: (input: CreatePromptProjectInput): Promise<PromptProject> =>
    request<PromptProject>("/prompt-projects", { method: "POST", body: input }),
  getPromptProject: (projectId: string): Promise<PromptProject> =>
    request<PromptProject>(`/prompt-projects/${projectId}`),
  renamePromptProject: (projectId: string, title: string): Promise<PromptProject> =>
    request<PromptProject>(`/prompt-projects/${projectId}`, { method: "PATCH", body: { title } }),
  updatePromptProjectWorkflow: (
    projectId: string,
    workflowProfileId: string,
    workflowMode: PromptWorkflowMode,
  ): Promise<PromptProject> =>
    request<PromptProject>(`/prompt-projects/${projectId}/workflow`, {
      method: "PATCH",
      body: { workflow_profile_id: workflowProfileId, workflow_mode: workflowMode },
    }),
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
  streamPromptDiscussion,
  getPromptProjectState: (projectId: string): Promise<PromptProjectState> =>
    request<PromptProjectState>(`/prompt-projects/${projectId}/state`),
  updatePromptProjectState: (
    projectId: string,
    input: UpdatePromptProjectStateInput,
  ): Promise<PromptProjectState> =>
    request<PromptProjectState>(`/prompt-projects/${projectId}/state`, { method: "PUT", body: input }),
  getPromptContextPreview: (projectId: string): Promise<PromptContextPreview> =>
    request<PromptContextPreview>(`/prompt-projects/${projectId}/context-preview`),
  listPromptRevisions: (projectId: string): Promise<PromptRevision[]> =>
    request<PromptRevision[]>(`/prompt-projects/${projectId}/revisions`),
  createPromptRevision: (projectId: string, input: CreatePromptRevisionInput): Promise<PromptRevision> =>
    request<PromptRevision>(`/prompt-projects/${projectId}/revisions`, { method: "POST", body: input }),
  acceptPromptRevision: (revisionId: string): Promise<PromptRevision> =>
    request<PromptRevision>(`/prompt-revisions/${revisionId}/accept`, { method: "POST" }),
  discardPromptRevision: (revisionId: string): Promise<PromptRevision> =>
    request<PromptRevision>(`/prompt-revisions/${revisionId}/discard`, { method: "POST" }),
};
