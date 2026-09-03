import { useCallback, useEffect, useMemo, useState } from "react";

import { controlApi } from "../api/controlApi";
import type {
  JsonValue,
  PromptMessage,
  PromptContextPreview,
  PromptProject,
  PromptProjectState,
  PromptRevision,
  PromptSession,
  PromptWorkflow,
  PromptWorkflowMode,
  UpdatePromptProjectStateInput,
} from "../api/controlApi";

interface WorkspaceData {
  project: PromptProject;
  sessions: PromptSession[];
  activeSessionId: string | null;
  messages: PromptMessage[];
  projectState: PromptProjectState;
  revisions: PromptRevision[];
}

interface StateDraft {
  objective: string;
  importantConstraints: string;
  mustPreserve: string;
  knownProblems: string;
  acceptedObservations: string;
}

interface RevisionDraft {
  positivePrompt: string;
  negativePrompt: string;
  parameters: string;
  changeLog: string;
}

const EMPTY_STATE_DRAFT: StateDraft = {
  objective: "",
  importantConstraints: "",
  mustPreserve: "",
  knownProblems: "",
  acceptedObservations: "",
};

const EMPTY_REVISION_DRAFT: RevisionDraft = {
  positivePrompt: "",
  negativePrompt: "",
  parameters: "{}",
  changeLog: "",
};

function linesToList(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function stateToDraft(projectState: PromptProjectState): StateDraft {
  return {
    objective: projectState.objective,
    importantConstraints: projectState.important_constraints.join("\n"),
    mustPreserve: projectState.must_preserve.join("\n"),
    knownProblems: projectState.known_problems.join("\n"),
    acceptedObservations: projectState.accepted_observations.join("\n"),
  };
}

function stateDraftToInput(draft: StateDraft): UpdatePromptProjectStateInput {
  return {
    objective: draft.objective.trim(),
    important_constraints: linesToList(draft.importantConstraints),
    must_preserve: linesToList(draft.mustPreserve),
    known_problems: linesToList(draft.knownProblems),
    accepted_observations: linesToList(draft.acceptedObservations),
  };
}

function formatUpdatedAt(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Unknown time" : date.toLocaleString();
}

function parseParameters(value: string): Record<string, JsonValue> | null {
  try {
    const parsed: unknown = JSON.parse(value);
    return parsed !== null && !Array.isArray(parsed) && typeof parsed === "object"
      ? (parsed as Record<string, JsonValue>)
      : null;
  } catch {
    return null;
  }
}

export function PromptWorkbenchPage() {
  const [projects, setProjects] = useState<PromptProject[]>([]);
  const [projectsStatus, setProjectsStatus] = useState<"loading" | "ready" | "error">("loading");
  const [workflows, setWorkflows] = useState<PromptWorkflow[]>([]);
  const [workflowsStatus, setWorkflowsStatus] = useState<"loading" | "ready" | "error">("loading");
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState<WorkspaceData | null>(null);
  const [workspaceStatus, setWorkspaceStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [notice, setNotice] = useState<string | null>(null);
  const [newProjectTitle, setNewProjectTitle] = useState("");
  const [renameTitle, setRenameTitle] = useState("");
  const [messageContent, setMessageContent] = useState("");
  const [stateDraft, setStateDraft] = useState<StateDraft>(EMPTY_STATE_DRAFT);
  const [revisionDraft, setRevisionDraft] = useState<RevisionDraft>(EMPTY_REVISION_DRAFT);
  const [contextPreview, setContextPreview] = useState<PromptContextPreview | null>(null);
  const [contextPreviewStatus, setContextPreviewStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [isSaving, setIsSaving] = useState(false);

  const loadProjects = useCallback(async () => {
    setProjectsStatus("loading");
    try {
      setProjects(await controlApi.listPromptProjects());
      setProjectsStatus("ready");
    } catch {
      setProjectsStatus("error");
    }
  }, []);

  const loadWorkflows = useCallback(async () => {
    setWorkflowsStatus("loading");
    try {
      setWorkflows(await controlApi.listPromptWorkflows());
      setWorkflowsStatus("ready");
    } catch {
      setWorkflowsStatus("error");
    }
  }, []);

  const loadWorkspace = useCallback(async (projectId: string) => {
    setWorkspaceStatus("loading");
    setNotice(null);
    try {
      const [project, sessions, projectState, revisions] = await Promise.all([
        controlApi.getPromptProject(projectId),
        controlApi.listPromptSessions(projectId),
        controlApi.getPromptProjectState(projectId),
        controlApi.listPromptRevisions(projectId),
      ]);
      const activeSessionId = project.active_session_id ?? sessions[0]?.id ?? null;
      const messages = activeSessionId ? await controlApi.listPromptMessages(activeSessionId) : [];
      setWorkspace({ project, sessions, activeSessionId, messages, projectState, revisions });
      setContextPreview(null);
      setContextPreviewStatus("idle");
      setRenameTitle(project.title);
      setStateDraft(stateToDraft(projectState));
      setWorkspaceStatus("ready");
    } catch {
      setWorkspace(null);
      setWorkspaceStatus("error");
    }
  }, []);

  useEffect(() => {
    void loadProjects();
    void loadWorkflows();
  }, [loadProjects, loadWorkflows]);

  const selectedCurrentRevision = useMemo(
    () => workspace?.revisions.find((revision) => revision.id === workspace.project.current_revision_id) ?? null,
    [workspace],
  );

  const proposedRevisions = useMemo(
    () => workspace?.revisions.filter((revision) => revision.status === "proposed") ?? [],
    [workspace],
  );

  const activeWorkflow = useMemo(
    () => workflows.find((workflow) => workflow.id === workspace?.project.workflow_profile_id) ?? null,
    [workflows, workspace?.project.workflow_profile_id],
  );

  async function handleCreateProject(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!newProjectTitle.trim()) {
      setNotice("Enter a project title before creating it.");
      return;
    }
    const defaultWorkflow = workflows[0];
    if (!defaultWorkflow) {
      setNotice("A built-in workflow must load before creating a project.");
      return;
    }

    setIsSaving(true);
    setNotice(null);
    try {
      const project = await controlApi.createPromptProject({
        title: newProjectTitle.trim(),
        workflow_profile_id: defaultWorkflow.id,
        workflow_mode: defaultWorkflow.default_mode,
      });
      setNewProjectTitle("");
      setSelectedProjectId(project.id);
      await Promise.all([loadProjects(), loadWorkspace(project.id)]);
    } catch {
      setNotice("The project could not be created. Check the local Controller API and retry.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleSelectProject(projectId: string) {
    setSelectedProjectId(projectId);
    await loadWorkspace(projectId);
  }

  async function handleWorkflowChange(workflowProfileId: string) {
    if (!workspace) {
      return;
    }
    const workflow = workflows.find((item) => item.id === workflowProfileId);
    if (!workflow) {
      setNotice("The selected workflow is unavailable.");
      return;
    }
    setIsSaving(true);
    setNotice(null);
    try {
      const project = await controlApi.updatePromptProjectWorkflow(
        workspace.project.id,
        workflow.id,
        workflow.default_mode,
      );
      setWorkspace((current) => (current ? { ...current, project } : current));
      setContextPreview(null);
      setContextPreviewStatus("idle");
      await loadProjects();
    } catch {
      setNotice("The workflow selection could not be saved.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleModeChange(workflowMode: PromptWorkflowMode) {
    if (!workspace) {
      return;
    }
    setIsSaving(true);
    setNotice(null);
    try {
      const project = await controlApi.updatePromptProjectWorkflow(
        workspace.project.id,
        workspace.project.workflow_profile_id,
        workflowMode,
      );
      setWorkspace((current) => (current ? { ...current, project } : current));
      setContextPreview(null);
      setContextPreviewStatus("idle");
      await loadProjects();
    } catch {
      setNotice("The workflow mode could not be saved.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleContextPreview() {
    if (!workspace) {
      return;
    }
    setContextPreviewStatus("loading");
    try {
      setContextPreview(await controlApi.getPromptContextPreview(workspace.project.id));
      setContextPreviewStatus("ready");
    } catch {
      setContextPreview(null);
      setContextPreviewStatus("error");
    }
  }

  async function handleRenameProject(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace || !renameTitle.trim()) {
      setNotice("A project title is required.");
      return;
    }

    setIsSaving(true);
    setNotice(null);
    try {
      const project = await controlApi.renamePromptProject(workspace.project.id, renameTitle.trim());
      setWorkspace((current) => (current ? { ...current, project } : current));
      await loadProjects();
    } catch {
      setNotice("The project name could not be saved.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleArchiveProject() {
    if (!workspace) {
      return;
    }

    setIsSaving(true);
    setNotice(null);
    try {
      await controlApi.archivePromptProject(workspace.project.id);
      setSelectedProjectId(null);
      setWorkspace(null);
      setWorkspaceStatus("idle");
      await loadProjects();
    } catch {
      setNotice("The project could not be archived.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleAppendMessage(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace?.activeSessionId || !messageContent.trim()) {
      setNotice("Enter a discussion note before saving it.");
      return;
    }

    setIsSaving(true);
    setNotice(null);
    try {
      const message = await controlApi.appendPromptMessage(workspace.activeSessionId, messageContent.trim());
      setWorkspace((current) => (current ? { ...current, messages: [...current.messages, message] } : current));
      setMessageContent("");
    } catch {
      setNotice("The discussion note could not be saved.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleSaveState(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace) {
      return;
    }

    setIsSaving(true);
    setNotice(null);
    try {
      const projectState = await controlApi.updatePromptProjectState(
        workspace.project.id,
        stateDraftToInput(stateDraft),
      );
      setWorkspace((current) => (current ? { ...current, projectState } : current));
      setStateDraft(stateToDraft(projectState));
      await loadProjects();
    } catch {
      setNotice("Project state could not be saved.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleCreateRevision(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace || !revisionDraft.positivePrompt.trim() || !revisionDraft.changeLog.trim()) {
      setNotice("Positive prompt and change log are required for a proposed revision.");
      return;
    }

    const parameters = parseParameters(revisionDraft.parameters);
    if (!parameters) {
      setNotice("Parameters must be a JSON object.");
      return;
    }

    setIsSaving(true);
    setNotice(null);
    try {
      await controlApi.createPromptRevision(workspace.project.id, {
        parent_revision_id: workspace.project.current_revision_id,
        positive_prompt: revisionDraft.positivePrompt.trim(),
        negative_prompt: revisionDraft.negativePrompt.trim(),
        parameters,
        change_log: revisionDraft.changeLog.trim(),
      });
      setRevisionDraft(EMPTY_REVISION_DRAFT);
      await Promise.all([loadProjects(), loadWorkspace(workspace.project.id)]);
    } catch {
      setNotice("The proposed revision could not be saved.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleRevisionAction(revisionId: string, action: "accept" | "discard") {
    if (!workspace) {
      return;
    }

    setIsSaving(true);
    setNotice(null);
    try {
      if (action === "accept") {
        await controlApi.acceptPromptRevision(revisionId);
      } else {
        await controlApi.discardPromptRevision(revisionId);
      }
      await Promise.all([loadProjects(), loadWorkspace(workspace.project.id)]);
    } catch {
      setNotice("The revision transition could not be completed.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <section className="page prompt-workbench-page" aria-labelledby="prompt-workbench-heading">
      <div className="page-heading-row">
        <div>
          <p className="eyebrow">Private local workspace</p>
          <h1 id="prompt-workbench-heading">Prompt Workbench</h1>
        </div>
        <p className="phase-note">Manual domain and persistence foundation — no LLM generation</p>
      </div>

      <div className="workbench-controls" aria-label="Prompt Workbench controls">
        <label>
          Workflow
          <select
            disabled={!workspace || workflowsStatus !== "ready" || isSaving}
            onChange={(event) => void handleWorkflowChange(event.target.value)}
            value={workspace?.project.workflow_profile_id ?? ""}
          >
            <option value="">Select a project</option>
            {workflows.map((workflow) => (
              <option key={workflow.id} value={workflow.id}>
                {workflow.display_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Mode
          <select
            disabled={!workspace || !activeWorkflow || isSaving}
            onChange={(event) => void handleModeChange(event.target.value as PromptWorkflowMode)}
            value={workspace?.project.workflow_mode ?? ""}
          >
            <option value="">Select a project</option>
            {(activeWorkflow?.supported_modes ?? []).map((mode) => (
              <option key={mode} value={mode}>
                {mode.slice(0, 1).toUpperCase() + mode.slice(1)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {workflowsStatus === "error" ? <p className="workbench-notice">Built-in workflows are unavailable.</p> : null}

      {notice ? (
        <p className="workbench-notice" role="status">
          {notice}
        </p>
      ) : null}

      <div className="prompt-workbench-grid prompt-workbench-grid--active">
        <section className="workbench-panel" aria-labelledby="projects-heading">
          <h2 id="projects-heading">Projects</h2>
          <form className="inline-form" onSubmit={handleCreateProject}>
            <label>
              New project title
              <input
                onChange={(event) => setNewProjectTitle(event.target.value)}
                placeholder="New Prompt Project"
                value={newProjectTitle}
              />
            </label>
            <button disabled={isSaving} type="submit">
              New Project
            </button>
          </form>

          {projectsStatus === "loading" ? <p role="status">Loading projects...</p> : null}
          {projectsStatus === "error" ? (
            <div className="message-box message-box--error">
              <p>Projects are unavailable.</p>
              <button className="secondary-button" onClick={() => void loadProjects()} type="button">
                Retry
              </button>
            </div>
          ) : null}
          {projectsStatus === "ready" && projects.length === 0 ? <p>No projects yet.</p> : null}
          <div className="project-list" aria-label="Prompt Projects">
            {projects.map((project) => (
              <button
                aria-pressed={selectedProjectId === project.id}
                className={selectedProjectId === project.id ? "project-list-item is-selected" : "project-list-item"}
                key={project.id}
                onClick={() => void handleSelectProject(project.id)}
                type="button"
              >
                <span>{project.title}</span>
                <small>Updated {formatUpdatedAt(project.updated_at)}</small>
              </button>
            ))}
          </div>

          {workspace ? (
            <div className="project-actions">
              <form className="inline-form" onSubmit={handleRenameProject}>
                <label>
                  Project name
                  <input onChange={(event) => setRenameTitle(event.target.value)} value={renameTitle} />
                </label>
                <button disabled={isSaving} type="submit">
                  Save name
                </button>
              </form>
              <button className="danger-button" disabled={isSaving} onClick={() => void handleArchiveProject()} type="button">
                Archive project
              </button>
            </div>
          ) : null}
        </section>

        <section className="workbench-panel" aria-labelledby="discussion-heading">
          <h2 id="discussion-heading">Discussion / Project State</h2>
          {workspaceStatus === "loading" ? <p role="status">Loading project workspace...</p> : null}
          {workspaceStatus === "error" && selectedProjectId ? (
            <div className="message-box message-box--error">
              <p>Project workspace is unavailable.</p>
              <button className="secondary-button" onClick={() => void loadWorkspace(selectedProjectId)} type="button">
                Retry
              </button>
            </div>
          ) : null}
          {!workspace && workspaceStatus === "idle" ? <p>Select a project to view its discussion and state.</p> : null}
          {workspace ? (
            <>
              <section className="revision-summary" aria-labelledby="knowledge-sources-heading">
                <h3 id="knowledge-sources-heading">Knowledge Sources</h3>
                {activeWorkflow ? (
                  <ul>
                    {activeWorkflow.knowledge_sources.map((source) => (
                      <li key={source.id}>
                        {source.label} <span className="phase-note">({source.stability})</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>Workflow knowledge sources are unavailable.</p>
                )}
              </section>
              <div className="discussion-history" aria-label="Discussion history">
                <h3>{workspace.sessions.find((item) => item.id === workspace.activeSessionId)?.title ?? "Discussion"}</h3>
                {workspace.messages.length === 0 ? <p>No discussion notes yet.</p> : null}
                {workspace.messages.map((message) => (
                  <article className="discussion-message" key={message.id}>
                    <strong>{message.role}</strong>
                    <p>{message.content}</p>
                  </article>
                ))}
              </div>
              <form className="stacked-form" onSubmit={handleAppendMessage}>
                <label>
                  Discussion note
                  <textarea
                    onChange={(event) => setMessageContent(event.target.value)}
                    placeholder="Add a manual discussion note"
                    rows={3}
                    value={messageContent}
                  />
                </label>
                <button disabled={isSaving || !workspace.activeSessionId} type="submit">
                  Save discussion note
                </button>
              </form>

              <form className="state-editor stacked-form" onSubmit={handleSaveState}>
                <h3>Project State</h3>
                <label>
                  Objective
                  <textarea
                    onChange={(event) => setStateDraft((current) => ({ ...current, objective: event.target.value }))}
                    rows={2}
                    value={stateDraft.objective}
                  />
                </label>
                <label>
                  Important constraints (one per line)
                  <textarea
                    onChange={(event) =>
                      setStateDraft((current) => ({ ...current, importantConstraints: event.target.value }))
                    }
                    rows={2}
                    value={stateDraft.importantConstraints}
                  />
                </label>
                <label>
                  Must preserve (one per line)
                  <textarea
                    onChange={(event) => setStateDraft((current) => ({ ...current, mustPreserve: event.target.value }))}
                    rows={2}
                    value={stateDraft.mustPreserve}
                  />
                </label>
                <label>
                  Known problems (one per line)
                  <textarea
                    onChange={(event) => setStateDraft((current) => ({ ...current, knownProblems: event.target.value }))}
                    rows={2}
                    value={stateDraft.knownProblems}
                  />
                </label>
                <label>
                  Accepted observations (one per line)
                  <textarea
                    onChange={(event) =>
                      setStateDraft((current) => ({ ...current, acceptedObservations: event.target.value }))
                    }
                    rows={2}
                    value={stateDraft.acceptedObservations}
                  />
                </label>
                <button disabled={isSaving} type="submit">
                  Save project state
                </button>
              </form>
            </>
          ) : null}
        </section>

        <section className="workbench-panel" aria-labelledby="artifact-heading">
          <h2 id="artifact-heading">Prompt Artifact</h2>
          {!workspace ? <p>Select a project to view revisions.</p> : null}
          {workspace ? (
            <>
              <section className="revision-summary" aria-labelledby="current-revision-heading">
                <h3 id="current-revision-heading">Current accepted revision</h3>
                {selectedCurrentRevision ? (
                  <p>
                    {selectedCurrentRevision.id} — {selectedCurrentRevision.change_log}
                  </p>
                ) : (
                  <p>No accepted revision.</p>
                )}
              </section>

              <section className="revision-summary" aria-labelledby="context-preview-heading">
                <h3 id="context-preview-heading">Context Preview</h3>
                <p>Contribution metadata only. This does not send a request to an LLM.</p>
                <button disabled={contextPreviewStatus === "loading"} onClick={() => void handleContextPreview()} type="button">
                  {contextPreviewStatus === "loading" ? "Loading preview..." : "Preview context"}
                </button>
                {contextPreviewStatus === "error" ? <p role="status">Context preview is unavailable.</p> : null}
                {contextPreview ? (
                  <ul aria-label="Context contributions">
                    {contextPreview.contributions.map((contribution) => (
                      <li key={`${contribution.kind}-${contribution.source}`}>
                        {contribution.label} — {contribution.stability}, {contribution.character_count} characters
                      </li>
                    ))}
                  </ul>
                ) : null}
              </section>

              <div className="revision-list" aria-label="Prompt revisions">
                {workspace.revisions.length === 0 ? <p>No revisions yet.</p> : null}
                {workspace.revisions.map((revision) => (
                  <article className="revision-item" key={revision.id}>
                    <div className="revision-item-heading">
                      <strong>{revision.status}</strong>
                      <span>{formatUpdatedAt(revision.created_at)}</span>
                    </div>
                    <p>{revision.change_log}</p>
                    <p>
                      <span className="revision-label">Positive:</span> {revision.positive_prompt}
                    </p>
                    <p>
                      <span className="revision-label">Negative:</span> {revision.negative_prompt || "None"}
                    </p>
                    {revision.status === "proposed" ? (
                      <div className="revision-actions">
                        <button disabled={isSaving} onClick={() => void handleRevisionAction(revision.id, "accept")} type="button">
                          Accept
                        </button>
                        <button
                          className="secondary-button"
                          disabled={isSaving}
                          onClick={() => void handleRevisionAction(revision.id, "discard")}
                          type="button"
                        >
                          Discard
                        </button>
                      </div>
                    ) : null}
                  </article>
                ))}
              </div>

              <form className="revision-form stacked-form" onSubmit={handleCreateRevision}>
                <h3>Propose manual revision</h3>
                <p>Manual entry only. This phase does not generate prompts.</p>
                <label>
                  Positive prompt
                  <textarea
                    onChange={(event) => setRevisionDraft((current) => ({ ...current, positivePrompt: event.target.value }))}
                    rows={3}
                    value={revisionDraft.positivePrompt}
                  />
                </label>
                <label>
                  Negative prompt
                  <textarea
                    onChange={(event) => setRevisionDraft((current) => ({ ...current, negativePrompt: event.target.value }))}
                    rows={2}
                    value={revisionDraft.negativePrompt}
                  />
                </label>
                <label>
                  Parameters (JSON object)
                  <textarea
                    onChange={(event) => setRevisionDraft((current) => ({ ...current, parameters: event.target.value }))}
                    rows={3}
                    value={revisionDraft.parameters}
                  />
                </label>
                <label>
                  Change log
                  <textarea
                    onChange={(event) => setRevisionDraft((current) => ({ ...current, changeLog: event.target.value }))}
                    rows={2}
                    value={revisionDraft.changeLog}
                  />
                </label>
                <button disabled={isSaving} type="submit">
                  Propose revision
                </button>
              </form>
              {proposedRevisions.length > 0 ? (
                <p className="phase-note">{proposedRevisions.length} proposed revision(s) awaiting an explicit decision.</p>
              ) : null}
            </>
          ) : null}
        </section>
      </div>
    </section>
  );
}
