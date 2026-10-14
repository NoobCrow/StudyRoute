import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { ChatPanel } from "./ChatPanel";
import { Badge } from "./Ui";

interface NavItem { to: string; label: string; roles: string[] }

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", roles: ["parent", "student", "admin"] },
  { to: "/compare", label: "Compare", roles: ["parent", "student"] },
  { to: "/payments", label: "Payments", roles: ["parent", "student", "admin"] },
  { to: "/recipients", label: "Recipients", roles: ["parent", "student"] },
  { to: "/documents", label: "Documents", roles: ["parent", "student"] },
  { to: "/audit", label: "Audit log", roles: ["parent", "admin"] },
  { to: "/rules", label: "Rules", roles: ["parent", "student", "admin"] },
  { to: "/sandbox", label: "Sandbox", roles: ["parent", "student", "admin"] },
];

export function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;
  const items = NAV.filter((item) => item.roles.includes(user.role));

  async function signOut() {
    await logout();
    navigate("/login");
  }

  return (
    <>
      <a className="skip-link" href="#main">Skip to content</a>
      <header className="app-header">
        <div className="inner">
          <NavLink to="/" className="brand" aria-label="StudyRoute home">
            <span className="brand-mark" aria-hidden="true" />
            StudyRoute
          </NavLink>
          <nav className="nav" aria-label="Main">
            {items.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.to === "/"}>
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="user-box">
            <span>{user.display_name}</span>
            <Badge tone="info">{user.role}</Badge>
            <button type="button" className="btn small" onClick={signOut}>Sign out</button>
          </div>
        </div>
      </header>
      <main id="main" className="page">
        <Outlet />
      </main>
      {user.role !== "admin" ? <ChatPanel /> : null}
    </>
  );
}
