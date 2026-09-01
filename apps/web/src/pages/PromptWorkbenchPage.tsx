export function PromptWorkbenchPage() {
  return (
    <section className="page prompt-workbench-page" aria-labelledby="prompt-workbench-heading">
      <div className="page-heading-row">
        <div>
          <p className="eyebrow">Workflow foundation</p>
          <h1 id="prompt-workbench-heading">Prompt Workbench</h1>
        </div>
        <p className="phase-note">Available in Phase 1</p>
      </div>

      <div className="workbench-controls" aria-label="Prompt Workbench controls">
        <label>
          Workflow
          <select defaultValue="planned" disabled>
            <option value="planned">Workflow selection — Available in Phase 1</option>
          </select>
        </label>
        <label>
          Mode
          <select defaultValue="balanced" disabled>
            <option value="stable">Stable</option>
            <option value="balanced">Balanced</option>
            <option value="detailed">Detailed</option>
            <option value="preserve">Preserve</option>
          </select>
        </label>
      </div>

      <div className="prompt-workbench-grid">
        <section className="workbench-panel" aria-labelledby="projects-heading">
          <div className="panel-heading-row">
            <h2 id="projects-heading">Projects</h2>
            <button disabled type="button">
              New Project — Available in Phase 1
            </button>
          </div>
          <p>No projects yet. Project and session storage begins in Phase 1.</p>
        </section>

        <section className="workbench-panel" aria-labelledby="discussion-heading">
          <h2 id="discussion-heading">Discussion / Request</h2>
          <p>Discussion messages will be associated with a Prompt Project and Prompt Session.</p>
          <textarea
            aria-label="Discussion placeholder"
            disabled
            placeholder="Available in Phase 1"
            rows={8}
          />
        </section>

        <section className="workbench-panel" aria-labelledby="artifact-heading">
          <h2 id="artifact-heading">Prompt Artifact</h2>
          <p>Current revision, positive prompt, negative prompt, and parameters will appear here.</p>
          <button disabled type="button">
            Copy Artifact — Available in Phase 1
          </button>
        </section>
      </div>
    </section>
  );
}
