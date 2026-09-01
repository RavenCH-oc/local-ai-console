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

class ControlApiRequestError extends Error {
  constructor() {
    super("The Controller API request did not succeed.");
    this.name = "ControlApiRequestError";
  }
}

async function request<T>(path: string): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`/api${path}`, {
      headers: {
        Accept: "application/json",
      },
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
};
