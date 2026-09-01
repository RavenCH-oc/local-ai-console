import { useCallback, useEffect, useState } from "react";

import { controlApi, type LlmRuntimeStatus } from "../../api/controlApi";

export type LlmRuntimeStatusLoadState = "checking" | "ready" | "unavailable";

export function useLlmRuntimeStatus() {
  const [state, setState] = useState<LlmRuntimeStatusLoadState>("checking");
  const [runtimeStatus, setRuntimeStatus] = useState<LlmRuntimeStatus | null>(null);

  const loadStatus = useCallback(async (probe: boolean) => {
    setState("checking");
    try {
      const nextStatus = probe ? await controlApi.probeLlmRuntimes() : await controlApi.getLlmRuntimeStatus();
      setRuntimeStatus(nextStatus);
      setState("ready");
    } catch {
      setState("unavailable");
    }
  }, []);

  useEffect(() => {
    void loadStatus(false);
  }, [loadStatus]);

  return {
    state,
    runtimeStatus,
    retry: () => loadStatus(true),
  };
}
