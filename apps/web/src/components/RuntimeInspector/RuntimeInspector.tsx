import type { ControllerConnectionState } from "../Status/useControllerHealth";
import type { LlmRuntimeSlotStatus } from "../../api/controlApi";
import { useLlmRuntimeStatus } from "./useLlmRuntimeStatus";

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

function runtimeMessage(status: LlmRuntimeSlotStatus): string {
  if (status.state === "unconfigured") {
    return "Unconfigured";
  }
  if (status.state === "unavailable") {
    return "Unavailable";
  }
  if (status.state === "checking") {
    return "Checking...";
  }
  if (status.state === "loading") {
    return "Loading";
  }
  if (status.state === "ready") {
    return "Ready";
  }
  if (status.error_code === "authentication_failure") {
    return "Authentication required";
  }
  if (["connection_failure", "timeout", "provider_failure"].includes(status.error_code ?? "")) {
    return "Unreachable";
  }
  return "Error";
}

export function RuntimeInspector({ controllerState, onRetryController }: RuntimeInspectorProps) {
  const llmRuntime = useLlmRuntimeStatus();

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

      <section className="inspector-section" aria-labelledby="main-llm-heading">
        <h3 id="main-llm-heading">Main LLM</h3>
        {llmRuntime.state === "ready" && llmRuntime.runtimeStatus ? (
          <p role="status">{runtimeMessage(llmRuntime.runtimeStatus.main)}</p>
        ) : llmRuntime.state === "unavailable" ? (
          <>
            <p role="status">Runtime status unavailable</p>
            <button className="secondary-button" onClick={llmRuntime.retry} type="button">
              Retry runtime status
            </button>
          </>
        ) : (
          <p role="status">Checking...</p>
        )}
      </section>

      <section className="inspector-section" aria-labelledby="utility-llm-heading">
        <h3 id="utility-llm-heading">Utility LLM</h3>
        {llmRuntime.state === "ready" && llmRuntime.runtimeStatus ? (
          <p role="status">{runtimeMessage(llmRuntime.runtimeStatus.utility)}</p>
        ) : (
          <p>{llmRuntime.state === "unavailable" ? "Unavailable" : "Checking..."}</p>
        )}
      </section>

      <section className="inspector-section" aria-labelledby="context-heading">
        <h3 id="context-heading">Context</h3>
        <p>Not available</p>
      </section>
    </aside>
  );
}
