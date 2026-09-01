import { useCallback, useEffect, useState } from "react";

import { controlApi } from "../../api/controlApi";

export type ControllerConnectionState = "checking" | "online" | "unavailable";

export interface ControllerHealthState {
  state: ControllerConnectionState;
  retry: () => void;
}

export function useControllerHealth(): ControllerHealthState {
  const [state, setState] = useState<ControllerConnectionState>("checking");
  const [requestNumber, setRequestNumber] = useState(0);

  const retry = useCallback(() => {
    setRequestNumber((currentRequestNumber) => currentRequestNumber + 1);
  }, []);

  useEffect(() => {
    let active = true;
    setState("checking");

    void controlApi
      .health()
      .then(() => {
        if (active) {
          setState("online");
        }
      })
      .catch(() => {
        if (active) {
          setState("unavailable");
        }
      });

    return () => {
      active = false;
    };
  }, [requestNumber]);

  return { state, retry };
}
