import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { App } from "../app/App";
import { controlApi } from "../api/controlApi";

vi.mock("../api/controlApi", () => ({
  controlApi: {
    health: vi.fn(),
    version: vi.fn(),
    runtimeInfo: vi.fn(),
  },
}));

const mockedControlApi = vi.mocked(controlApi);

const healthResponse = {
  status: "ok" as const,
  service: "control-api",
  version: "0.1.0.dev0",
};

const versionResponse = {
  application: "Local AI Console",
  service: "control-api",
  version: "0.1.0.dev0",
};

const runtimeInfoResponse = {
  root: "C:\\Runtime\\LocalAIConsole",
  source: "windows_default" as const,
  initialized: true,
  paths: {
    config: "C:\\Runtime\\LocalAIConsole\\config",
    data: "C:\\Runtime\\LocalAIConsole\\data",
    prompts: "C:\\Runtime\\LocalAIConsole\\prompts",
    knowledge: "C:\\Runtime\\LocalAIConsole\\knowledge",
    logs: "C:\\Runtime\\LocalAIConsole\\logs",
    cache: "C:\\Runtime\\LocalAIConsole\\cache",
    backups: "C:\\Runtime\\LocalAIConsole\\backups",
  },
};

function configureAvailableApi() {
  mockedControlApi.health.mockResolvedValue(healthResponse);
  mockedControlApi.version.mockResolvedValue(versionResponse);
  mockedControlApi.runtimeInfo.mockResolvedValue(runtimeInfoResponse);
}

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App />);
}

describe("Local AI Console web shell", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    configureAvailableApi();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders Home with the primary navigation and an online Controller", async () => {
    renderAt("/");

    expect(screen.getByRole("heading", { name: "Local AI Console" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Prompt Workbench" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Personal" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Discord Bot" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Waifu Bot" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute("aria-current", "page");
    expect(await screen.findByText("Controller: Online")).toBeInTheDocument();
    expect(screen.getByText("Not connected yet")).toBeInTheDocument();
  });

  it("navigates to the first-class Prompt Workbench route and shows its three-part skeleton", async () => {
    const user = userEvent.setup();
    renderAt("/");

    await user.click(screen.getByRole("link", { name: "Prompt Workbench" }));

    expect(await screen.findByRole("heading", { name: "Prompt Workbench" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Projects" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Discussion / Request" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Prompt Artifact" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Prompt Workbench" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: /New Project/ })).toBeDisabled();
    expect(screen.getByLabelText("Mode")).toBeDisabled();
  });

  it("loads Settings with safe Controller Runtime metadata", async () => {
    renderAt("/settings");

    expect(screen.getByText("Loading runtime info...")).toBeInTheDocument();
    expect(await screen.findByText("Controller Runtime")).toBeInTheDocument();
    expect(screen.getByText("0.1.0.dev0")).toBeInTheDocument();
    expect(screen.getByText("C:\\Runtime\\LocalAIConsole")).toBeInTheDocument();
    expect(screen.getByText("Windows default")).toBeInTheDocument();
  });

  it("keeps the shell usable when the Controller is unreachable and retries health", async () => {
    mockedControlApi.health.mockRejectedValue(new Error("unreachable"));
    renderAt("/");

    expect(await screen.findByText("Controller unavailable")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(mockedControlApi.health).toHaveBeenCalledTimes(2));
  });

  it("shows a readable Settings error and retries runtime metadata", async () => {
    mockedControlApi.runtimeInfo.mockRejectedValueOnce(new Error("unavailable"));
    mockedControlApi.runtimeInfo.mockResolvedValueOnce(runtimeInfoResponse);
    renderAt("/settings");

    expect(await screen.findByRole("heading", { name: "Runtime metadata unavailable" })).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Controller Runtime")).toBeInTheDocument();
    expect(mockedControlApi.runtimeInfo).toHaveBeenCalledTimes(2);
  });
});
