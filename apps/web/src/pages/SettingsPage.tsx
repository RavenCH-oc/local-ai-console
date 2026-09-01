import { useCallback, useEffect, useState } from "react";

import { controlApi } from "../api/controlApi";
import type { RuntimeInfoResponse, VersionResponse } from "../api/controlApi";

type RuntimeInfoLoadState =
  | { status: "loading" }
  | { status: "ready"; runtimeInfo: RuntimeInfoResponse; version: VersionResponse }
  | { status: "error" };

function sourceLabel(source: RuntimeInfoResponse["source"]): string {
  return source === "windows_default" ? "Windows default" : "Environment override";
}

export function SettingsPage() {
  const [loadState, setLoadState] = useState<RuntimeInfoLoadState>({ status: "loading" });

  const loadRuntimeInfo = useCallback(async () => {
    setLoadState({ status: "loading" });

    try {
      const [version, runtimeInfo] = await Promise.all([controlApi.version(), controlApi.runtimeInfo()]);
      setLoadState({ status: "ready", version, runtimeInfo });
    } catch {
      setLoadState({ status: "error" });
    }
  }, []);

  useEffect(() => {
    void loadRuntimeInfo();
  }, [loadRuntimeInfo]);

  return (
    <section className="page" aria-labelledby="settings-heading">
      <p className="eyebrow">Controller metadata</p>
      <h1 id="settings-heading">Settings</h1>
      <p className="page-lead">Read-only, non-sensitive Controller Runtime metadata.</p>

      {loadState.status === "loading" ? <p role="status">Loading runtime info...</p> : null}

      {loadState.status === "error" ? (
        <section className="message-box message-box--error" aria-labelledby="runtime-info-error-heading">
          <h2 id="runtime-info-error-heading">Runtime metadata unavailable</h2>
          <p>The Controller API could not provide runtime information. Check the local service and try again.</p>
          <button className="secondary-button" onClick={() => void loadRuntimeInfo()} type="button">
            Retry
          </button>
        </section>
      ) : null}

      {loadState.status === "ready" ? (
        <section className="metadata-section" aria-labelledby="runtime-metadata-heading">
          <h2 id="runtime-metadata-heading">Controller Runtime</h2>
          <dl className="metadata-list">
            <div>
              <dt>Application version</dt>
              <dd>{loadState.version.version}</dd>
            </div>
            <div>
              <dt>Runtime root</dt>
              <dd>{loadState.runtimeInfo.root}</dd>
            </div>
            <div>
              <dt>Runtime source</dt>
              <dd>{sourceLabel(loadState.runtimeInfo.source)}</dd>
            </div>
            <div>
              <dt>Initialized</dt>
              <dd>{loadState.runtimeInfo.initialized ? "Yes" : "No"}</dd>
            </div>
          </dl>

          <h3>Runtime layout</h3>
          <dl className="metadata-list metadata-list--paths">
            {Object.entries(loadState.runtimeInfo.paths).map(([name, path]) => (
              <div key={name}>
                <dt>{name}</dt>
                <dd>{path}</dd>
              </div>
            ))}
          </dl>
        </section>
      ) : null}
    </section>
  );
}
