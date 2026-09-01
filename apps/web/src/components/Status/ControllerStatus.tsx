import type { ControllerConnectionState } from "./useControllerHealth";

interface ControllerStatusProps {
  state: ControllerConnectionState;
}

const statusText: Record<ControllerConnectionState, string> = {
  checking: "Checking",
  online: "Online",
  unavailable: "Unavailable",
};

export function ControllerStatus({ state }: ControllerStatusProps) {
  return (
    <p className={`controller-status controller-status--${state}`} role="status">
      <span aria-hidden="true" className="status-indicator" />
      <span>Controller: {statusText[state]}</span>
    </p>
  );
}
