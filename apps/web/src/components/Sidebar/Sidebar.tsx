import { NavLink } from "react-router-dom";

interface NavigationItemProps {
  to: string;
  children: string;
  end?: boolean;
}

function NavigationItem({ to, children, end = false }: NavigationItemProps) {
  return (
    <NavLink className={({ isActive }) => (isActive ? "sidebar-link is-active" : "sidebar-link")} end={end} to={to}>
      {children}
    </NavLink>
  );
}

export function Sidebar() {
  return (
    <nav aria-label="Primary navigation" className="sidebar">
      <div className="sidebar-group">
        <NavigationItem end to="/">
          Home
        </NavigationItem>
        <NavigationItem to="/personal">Personal</NavigationItem>
      </div>

      <div className="sidebar-group">
        <p className="sidebar-label">Tools</p>
        <NavigationItem to="/tools/prompt-workbench">Prompt Workbench</NavigationItem>
      </div>

      <div className="sidebar-group">
        <p className="sidebar-label">Services</p>
        <NavigationItem to="/services/discord">Discord Bot</NavigationItem>
        <NavigationItem to="/services/waifu">Waifu Bot</NavigationItem>
      </div>

      <div className="sidebar-footer">
        <NavigationItem to="/settings">Settings</NavigationItem>
      </div>
    </nav>
  );
}
