import { Link, Outlet } from "react-router-dom";

import { RuntimeInspector } from "../RuntimeInspector/RuntimeInspector";
import { Sidebar } from "../Sidebar/Sidebar";
import { ControllerStatus } from "../Status/ControllerStatus";
import { useControllerHealth } from "../Status/useControllerHealth";

export function AppShell() {
  const controllerHealth = useControllerHealth();

  return (
    <div className="app-frame">
      <header className="app-header">
        <Link className="product-name" to="/">
          Local AI Console
        </Link>
        <ControllerStatus state={controllerHealth.state} />
      </header>

      <div className="app-layout">
        <Sidebar />
        <main className="workspace" id="workspace">
          <Outlet context={{ controllerState: controllerHealth.state }} />
        </main>
        <RuntimeInspector controllerState={controllerHealth.state} onRetryController={controllerHealth.retry} />
      </div>
    </div>
  );
}
