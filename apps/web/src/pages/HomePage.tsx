import { useOutletContext } from "react-router-dom";

import type { ControllerConnectionState } from "../components/Status/useControllerHealth";

interface HomePageOutletContext {
  controllerState: ControllerConnectionState;
}

function controllerStatusLabel(state: ControllerConnectionState): string {
  if (state === "online") {
    return "Online";
  }

  if (state === "unavailable") {
    return "Unavailable";
  }

  return "Checking";
}

export function HomePage() {
  const { controllerState } = useOutletContext<HomePageOutletContext>();

  return (
    <section className="page" aria-labelledby="home-heading">
      <p className="eyebrow">Local-first controller</p>
      <h1 id="home-heading">Local AI Console</h1>
      <p className="page-lead">
        An early-development workspace for local AI runtime and workflow management.
      </p>

      <div className="foundation-grid">
        <section className="foundation-item" aria-labelledby="api-status-heading">
          <h2 id="api-status-heading">Control API status</h2>
          <p>{controllerStatusLabel(controllerState)}</p>
        </section>
        <section className="foundation-item" aria-labelledby="status-heading">
          <h2 id="status-heading">Development status</h2>
          <p>Phase 0 foundation in progress. Runtime and workflow features are not available yet.</p>
        </section>
        <section className="foundation-item" aria-labelledby="next-heading">
          <h2 id="next-heading">Next main direction</h2>
          <p>Prompt Workbench will become the first local workflow surface after the foundation phase.</p>
        </section>
      </div>
    </section>
  );
}
