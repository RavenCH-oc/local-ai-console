import type { ControllerConnectionState } from "../Status/useControllerHealth";

interface RuntimeInspectorProps {
  controllerState: ControllerConnectionState;
  onRetryController: () => void;
}

function controllerMessage(state: ControllerConnectionState): string {
  if (state === "online") {
    return "Online";
  }

  if (state === "unavailable") {
    return "Controller unavailable";
  }

  return "Checking...";
}

export function RuntimeInspector({ controllerState, onRetryController }: RuntimeInspectorProps) {
  return (
    <aside aria-labelledby="runtime-inspector-heading" className="runtime-inspector">
      <h2 id="runtime-inspector-heading">Runtime Inspector</h2>

      <section className="inspector-section" aria-labelledby="controller-heading">
        <h3 id="controller-heading">Controller</h3>
        <p className={`inspector-status inspector-status--${controllerState}`} role="status">
          {controllerMessage(controllerState)}
        </p>
        {controllerState === "unavailable" ? (
          <button className="secondary-button" onClick={onRetryController} type="button">
            Retry
          </button>
        ) : null}
      </section>

      <section className="inspector-section" aria-labelledby="llm-pc-heading">
        <h3 id="llm-pc-heading">LLM PC</h3>
        <p>Not connected yet</p>
      </section>

      <section className="inspector-section" aria-labelledby="model-heading">
        <h3 id="model-heading">Model</h3>
        <p>No model runtime configured</p>
      </section>

      <section className="inspector-section" aria-labelledby="context-heading">
        <h3 id="context-heading">Context</h3>
        <p>Not available</p>
      </section>
    </aside>
  );
}
