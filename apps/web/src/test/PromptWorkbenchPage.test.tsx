import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { controlApi } from "../api/controlApi";
import type {
  PromptContextPreview,
  PromptDiscussionStreamCallbacks,
  PromptMessage,
  PromptProject,
  PromptProjectState,
  PromptRevision,
  PromptSession,
  PromptWorkflow,
} from "../api/controlApi";
import { PromptWorkbenchPage } from "../pages/PromptWorkbenchPage";

vi.mock("../api/controlApi", () => ({
  ControlApiRequestError: class ControlApiRequestError extends Error {},
  controlApi: {
    listPromptProjects: vi.fn(),
    listPromptWorkflows: vi.fn(),
    createPromptProject: vi.fn(),
    getPromptProject: vi.fn(),
    renamePromptProject: vi.fn(),
    updatePromptProjectWorkflow: vi.fn(),
    archivePromptProject: vi.fn(),
    listPromptSessions: vi.fn(),
    createPromptSession: vi.fn(),
    listPromptMessages: vi.fn(),
    appendPromptMessage: vi.fn(),
    streamPromptDiscussion: vi.fn(),
    getPromptProjectState: vi.fn(),
    updatePromptProjectState: vi.fn(),
    getPromptContextPreview: vi.fn(),
    listPromptRevisions: vi.fn(),
    createPromptRevision: vi.fn(),
    acceptPromptRevision: vi.fn(),
    discardPromptRevision: vi.fn(),
  },
}));

const api = vi.mocked(controlApi);

const project = (overrides: Partial<PromptProject> = {}): PromptProject => ({
  id: "pp_test_project",
  title: "Sanitized test project",
  workflow_profile_id: "anima_base_v1",
  workflow_mode: "balanced",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
  active_session_id: "ps_test_session",
  current_revision_id: null,
  status: "active",
  archived_at: null,
  ...overrides,
});

const session: PromptSession = {
  id: "ps_test_session",
  project_id: "pp_test_project",
  title: "Initial discussion",
  status: "active",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
};

const projectState: PromptProjectState = {
  id: "pst_test_state",
  project_id: "pp_test_project",
  objective: "",
  important_constraints: [],
  must_preserve: [],
  known_problems: [],
  accepted_observations: [],
  updated_at: "2026-09-01T00:00:00Z",
};

const proposedRevision = (overrides: Partial<PromptRevision> = {}): PromptRevision => ({
  id: "pr_test_revision",
  project_id: "pp_test_project",
  parent_revision_id: null,
  positive_prompt: "generic subject",
  negative_prompt: "artifacts",
  parameters: {},
  change_log: "Sanitized manual proposal.",
  status: "proposed",
  created_at: "2026-09-01T00:00:00Z",
  ...overrides,
});

const workflow: PromptWorkflow = {
  id: "anima_base_v1",
  display_name: "Anima Base v1",
  model_family: "anima_base_v1",
  supported_modes: ["stable", "balanced", "detailed", "preserve"],
  default_mode: "balanced",
  knowledge_sources: [
    { id: "anima_base_v1_fundamentals", label: "Fundamentals", source_kind: "built_in", stability: "stable" },
    { id: "anima_base_v1_parameters", label: "Parameters", source_kind: "built_in", stability: "stable" },
  ],
};

const contextPreview: PromptContextPreview = {
  workflow_profile_id: "anima_base_v1",
  workflow_mode: "balanced",
  contributions: [
    {
      label: "Base System",
      kind: "instruction",
      source: "prompt_workbench_base",
      stability: "stable",
      character_count: 120,
      token_count: null,
    },
    {
      label: "Current Request",
      kind: "current_request",
      source: "current_user_message",
      stability: "dynamic",
      character_count: 40,
      token_count: null,
    },
  ],
};

function configureWorkspace(
  selectedProject: PromptProject = project(),
  revisions: PromptRevision[] = [],
  selectedState: PromptProjectState = projectState,
) {
  api.getPromptProject.mockResolvedValue(selectedProject);
  api.listPromptSessions.mockResolvedValue([session]);
  api.getPromptProjectState.mockResolvedValue(selectedState);
  api.listPromptRevisions.mockResolvedValue(revisions);
  api.listPromptMessages.mockResolvedValue([]);
}

async function selectProject(user: ReturnType<typeof userEvent.setup>, title = "Sanitized test project") {
  await user.click(await screen.findByRole("button", { name: new RegExp(title) }));
  await screen.findByText("No discussion notes yet.");
}

describe("Prompt Workbench persistence UI", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listPromptProjects.mockResolvedValue([]);
    api.listPromptWorkflows.mockResolvedValue([workflow]);
    api.updatePromptProjectWorkflow.mockResolvedValue(project());
    api.getPromptContextPreview.mockResolvedValue(contextPreview);
    api.streamPromptDiscussion.mockResolvedValue(undefined);
    configureWorkspace();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders an empty project state", async () => {
    render(<PromptWorkbenchPage />);

    expect(await screen.findByText("No projects yet.")).toBeInTheDocument();
    expect(screen.getByText("Select a project to view its discussion and state.")).toBeInTheDocument();
  });

  it("creates a project and loads its persistent workspace", async () => {
    const user = userEvent.setup();
    const created = project({ title: "Created project" });
    api.listPromptProjects.mockResolvedValueOnce([]).mockResolvedValue([created]);
    api.createPromptProject.mockResolvedValue(created);
    api.getPromptProject.mockResolvedValue(created);
    render(<PromptWorkbenchPage />);

    await user.type(await screen.findByLabelText("New project title"), "Created project");
    await user.click(screen.getByRole("button", { name: "New Project" }));

    await screen.findByDisplayValue("Created project");
      expect(api.createPromptProject).toHaveBeenCalledWith({
        title: "Created project",
        workflow_profile_id: "anima_base_v1",
        workflow_mode: "balanced",
      });
  });

  it("selects a project and saves typed project state", async () => {
    const user = userEvent.setup();
    api.listPromptProjects.mockResolvedValue([project()]);
    const savedState: PromptProjectState = {
      ...projectState,
      objective: "Persist this objective",
      must_preserve: ["Readable composition"],
    };
    api.updatePromptProjectState.mockResolvedValue(savedState);
    render(<PromptWorkbenchPage />);

    await selectProject(user);
    await user.type(screen.getByLabelText("Objective"), "Persist this objective");
    await user.type(screen.getByLabelText("Must preserve (one per line)"), "Readable composition");
    await user.click(screen.getByRole("button", { name: "Save project state" }));

    await waitFor(() =>
      expect(api.updatePromptProjectState).toHaveBeenCalledWith("pp_test_project", {
        objective: "Persist this objective",
        important_constraints: [],
        must_preserve: ["Readable composition"],
        known_problems: [],
        accepted_observations: [],
      }),
    );
  });

  it("shows an enabled Send button while discussion generation is inactive", async () => {
    const user = userEvent.setup();
    api.listPromptProjects.mockResolvedValue([project()]);
    render(<PromptWorkbenchPage />);

    await selectProject(user);
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
  });

  it("keeps the composer stable while reasoning and text deltas stream, then reloads the persisted assistant message", async () => {
    const user = userEvent.setup();
    api.listPromptProjects.mockResolvedValue([project()]);
    const persistedAssistant: PromptMessage = {
      id: "pm_assistant",
      session_id: session.id,
      role: "assistant",
      content: "Visible discussion answer.",
      metadata: { discussion_generation: { reasoning_content: "Persisted reasoning." } },
      created_at: "2026-09-01T00:00:01Z",
    };
    api.listPromptMessages
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        {
          id: "pm_user",
          session_id: session.id,
          role: "user",
          content: "Discuss the prompt.",
          metadata: null,
          created_at: "2026-09-01T00:00:00Z",
        },
        persistedAssistant,
      ]);
    let callbacks: PromptDiscussionStreamCallbacks | undefined;
    let finishStream: (() => void) | undefined;
    api.streamPromptDiscussion.mockImplementation((_sessionId, _input, activeCallbacks) => {
      callbacks = activeCallbacks;
      callbacks.started({ user_message_id: "pm_user", input_tokens: 123, max_output_tokens: 1024 });
      callbacks.reasoningDelta("Streaming reasoning.");
      callbacks.reasoningDelta(" More reasoning.");
      callbacks.textDelta("Streaming visible answer.");
      callbacks.textDelta(" More visible text.");
      return new Promise<void>((resolve) => {
        finishStream = resolve;
      });
    });
    render(<PromptWorkbenchPage />);

    await selectProject(user);
    const composer = screen.getByLabelText("Discussion message");
    await user.type(composer, "Discuss the prompt.");
    await user.selectOptions(screen.getByLabelText("Thinking"), "on");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Streaming visible answer. More visible text.")).toBeInTheDocument();
    expect(screen.getByText("Streaming reasoning. More reasoning.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Stop" })).toBeEnabled();
    expect(screen.getByLabelText("Discussion message")).toBe(composer);
    expect(composer).toBeDisabled();
    expect(api.createPromptRevision).not.toHaveBeenCalled();

    callbacks?.completed({ assistant_message_id: persistedAssistant.id, finish_reason: "stop", input_tokens: 123 });
    finishStream?.();

    expect(await screen.findByText("Visible discussion answer.")).toBeInTheDocument();
    expect(screen.getByText("Persisted reasoning.")).toBeInTheDocument();
    expect(api.streamPromptDiscussion).toHaveBeenCalledWith(
      session.id,
      { content: "Discuss the prompt.", thinking_mode: "on" },
      expect.any(Object),
      expect.any(AbortSignal),
    );
  });

  it("stops a partial discussion, restores Send, and does not display a completed assistant", async () => {
    const user = userEvent.setup();
    api.listPromptProjects.mockResolvedValue([project()]);
    let callbacks: PromptDiscussionStreamCallbacks | undefined;
    api.streamPromptDiscussion.mockImplementation((_sessionId, _input, activeCallbacks, signal) => {
      callbacks = activeCallbacks;
      callbacks.started({ user_message_id: "pm_user", input_tokens: 123, max_output_tokens: 1024 });
      callbacks.reasoningDelta("Partial reasoning.");
      callbacks.textDelta("Incomplete assistant text.");
      return new Promise<void>((resolve) =>
        signal.addEventListener(
          "abort",
          () => {
            callbacks?.cancelled();
            resolve();
          },
          { once: true },
        ),
      );
    });
    render(<PromptWorkbenchPage />);

    await selectProject(user);
    await user.type(screen.getByLabelText("Discussion message"), "Stop this discussion.");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Incomplete assistant text.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Stop" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Stop" }));

    expect(await screen.findByText("Discussion stopped. The incomplete assistant response was not saved.")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Send" })).toBeEnabled();
    expect(screen.queryByText("Incomplete assistant text.")).not.toBeInTheDocument();
    expect(api.createPromptRevision).not.toHaveBeenCalled();
  });

  it("renders a sanitized preflight error and returns to Send state", async () => {
    const user = userEvent.setup();
    api.listPromptProjects.mockResolvedValue([project()]);
    api.streamPromptDiscussion.mockImplementation(async (_sessionId, _input, callbacks) => {
      callbacks.error({ code: "input_token_preflight_failed", message: "Input-token preflight failed." });
    });
    render(<PromptWorkbenchPage />);

    await selectProject(user);
    await user.type(screen.getByLabelText("Discussion message"), "Test provider error.");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Input-token preflight failed.")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Send" })).toBeInTheDocument();
    expect(api.createPromptRevision).not.toHaveBeenCalled();
  });

  it("loads built-in workflow metadata, persists mode selection, and exposes context preview", async () => {
    const user = userEvent.setup();
    api.listPromptProjects.mockResolvedValue([project()]);
    api.updatePromptProjectWorkflow.mockResolvedValue(project({ workflow_mode: "preserve" }));
    render(<PromptWorkbenchPage />);

    await selectProject(user);
    expect(screen.getByLabelText("Workflow")).toHaveDisplayValue("Anima Base v1");
    expect(screen.getByLabelText("Mode")).toHaveDisplayValue("Balanced");
    expect(screen.getByText("Fundamentals")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Mode"), "preserve");
    await waitFor(() =>
      expect(api.updatePromptProjectWorkflow).toHaveBeenCalledWith("pp_test_project", "anima_base_v1", "preserve"),
    );

    await user.click(screen.getByRole("button", { name: "Preview context" }));
    expect(await screen.findByText(/Base System — stable, 120 characters/)).toBeInTheDocument();
    expect(api.getPromptContextPreview).toHaveBeenCalledWith("pp_test_project");
  });

  it("creates a manual proposed revision", async () => {
    const user = userEvent.setup();
    const revision = proposedRevision();
    api.listPromptProjects.mockResolvedValue([project()]);
    api.listPromptRevisions.mockResolvedValueOnce([]).mockResolvedValue([revision]);
    api.createPromptRevision.mockResolvedValue(revision);
    render(<PromptWorkbenchPage />);

    await selectProject(user);
    await user.type(screen.getByLabelText("Positive prompt"), "generic subject");
    await user.type(screen.getByLabelText("Change log"), "Manual proposal");
    await user.click(screen.getByRole("button", { name: "Propose revision" }));

    await waitFor(() =>
      expect(api.createPromptRevision).toHaveBeenCalledWith("pp_test_project", {
        parent_revision_id: null,
        positive_prompt: "generic subject",
        negative_prompt: "",
        parameters: {},
        change_log: "Manual proposal",
      }),
    );
  });

  it("accepts a proposed revision and refetches the project pointer", async () => {
    const user = userEvent.setup();
    const proposal = proposedRevision();
    const acceptedProject = project({ current_revision_id: proposal.id });
    const acceptedRevision = proposedRevision({ status: "accepted" });
    api.listPromptProjects.mockResolvedValue([project()]);
    api.getPromptProject.mockResolvedValueOnce(project()).mockResolvedValue(acceptedProject);
    api.listPromptRevisions.mockResolvedValueOnce([proposal]).mockResolvedValue([acceptedRevision]);
    api.acceptPromptRevision.mockResolvedValue(acceptedRevision);
    render(<PromptWorkbenchPage />);

    await selectProject(user);
    await user.click(screen.getByRole("button", { name: "Accept" }));

    await waitFor(() => expect(api.acceptPromptRevision).toHaveBeenCalledWith(proposal.id));
    expect(await screen.findByText(new RegExp(acceptedProject.current_revision_id ?? ""))).toBeInTheDocument();
  });

  it("discards a proposed revision", async () => {
    const user = userEvent.setup();
    const proposal = proposedRevision();
    api.listPromptProjects.mockResolvedValue([project()]);
    api.listPromptRevisions.mockResolvedValueOnce([proposal]).mockResolvedValue([proposedRevision({ status: "discarded" })]);
    api.discardPromptRevision.mockResolvedValue(proposedRevision({ status: "discarded" }));
    render(<PromptWorkbenchPage />);

    await selectProject(user);
    await user.click(screen.getByRole("button", { name: "Discard" }));

    await waitFor(() => expect(api.discardPromptRevision).toHaveBeenCalledWith(proposal.id));
    expect(await screen.findByText("discarded")).toBeInTheDocument();
  });

  it("refetches persisted fake API data after a remount", async () => {
    const persistedProject = project({ title: "Persisted fake project" });
    api.listPromptProjects.mockResolvedValue([persistedProject]);
    const first = render(<PromptWorkbenchPage />);
    expect(await screen.findByRole("button", { name: /Persisted fake project/ })).toBeInTheDocument();
    first.unmount();

    render(<PromptWorkbenchPage />);
    expect(await screen.findByRole("button", { name: /Persisted fake project/ })).toBeInTheDocument();
    expect(api.listPromptProjects).toHaveBeenCalledTimes(2);
  });
});
