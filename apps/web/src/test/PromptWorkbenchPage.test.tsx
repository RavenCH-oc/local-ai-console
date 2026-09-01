import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { controlApi } from "../api/controlApi";
import type { PromptProject, PromptProjectState, PromptRevision, PromptSession } from "../api/controlApi";
import { PromptWorkbenchPage } from "../pages/PromptWorkbenchPage";

vi.mock("../api/controlApi", () => ({
  controlApi: {
    listPromptProjects: vi.fn(),
    createPromptProject: vi.fn(),
    getPromptProject: vi.fn(),
    renamePromptProject: vi.fn(),
    archivePromptProject: vi.fn(),
    listPromptSessions: vi.fn(),
    createPromptSession: vi.fn(),
    listPromptMessages: vi.fn(),
    appendPromptMessage: vi.fn(),
    getPromptProjectState: vi.fn(),
    updatePromptProjectState: vi.fn(),
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
  workflow_profile_id: "example_image_prompt_workflow",
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
    expect(api.createPromptProject).toHaveBeenCalledWith({ title: "Created project" });
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
