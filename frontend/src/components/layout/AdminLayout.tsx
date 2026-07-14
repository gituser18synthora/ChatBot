import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { chatApi } from "@/api/services";
import { useAuth } from "@/context/AuthContext";
import { Icon } from "@/components/ui/Icons";
import { cn, initials, roleLabel } from "@/lib/utils";
import type { Role } from "@/api/types";

interface NavItem {
  to: string;
  label: string;
  icon: (p: any) => ReactNode;
  roles?: Role[]; // if omitted, all admins
}

const NAV: NavItem[] = [
  { to: "/admin", label: "Dashboard", icon: Icon.Dashboard },
  { to: "/admin/tenants", label: "Tenants", icon: Icon.Building, roles: ["super_admin"] },
  { to: "/admin/knowledge-bases", label: "Knowledge Bases", icon: Icon.Book },
  { to: "/admin/documents", label: "Documents", icon: Icon.Doc },
  { to: "/admin/users", label: "Users", icon: Icon.Users },
  { to: "/admin/conversations", label: "Conversations", icon: Icon.Chat },
  { to: "/admin/analytics", label: "Usage & Costs", icon: Icon.Chart },
  { to: "/admin/audit-logs", label: "Audit Logs", icon: Icon.Shield },
  { to: "/admin/settings", label: "Settings", icon: Icon.Settings },
];

function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-5 py-5">
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 text-white shadow-sm">
        <Icon.Sparkle width={18} height={18} />
      </div>
      <div className="leading-tight">
        <p className="text-sm font-bold text-slate-900">Aurexion</p>
        <p className="text-[11px] font-medium text-slate-400">Admin Console</p>
      </div>
    </div>
  );
}

export function AdminLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [drawer, setDrawer] = useState(false);
  const [menu, setMenu] = useState(false);
  // Chat requires at least one Knowledge Base. `null` while unknown so we don't
  // flash the button disabled before the check resolves. Super Admins don't chat.
  const [chatAllowed, setChatAllowed] = useState<boolean | null>(null);

  useEffect(() => {
    if (!user || user.role === "super_admin") return;
    let ok = true;
    chatApi
      .availability()
      .then((r) => ok && setChatAllowed(r.has_knowledge_base))
      .catch(() => ok && setChatAllowed(null));
    return () => {
      ok = false;
    };
  }, [user]);

  const visible = NAV.filter((n) => !n.roles || (user && n.roles.includes(user.role)));

  const SidebarContent = (
    <div className="flex h-full flex-col">
      <Brand />
      <nav className="flex-1 space-y-1 overflow-y-auto px-3 pb-4">
        {visible.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.to === "/admin"}
            onClick={() => setDrawer(false)}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition",
                isActive
                  ? "bg-brand-50 text-brand-700"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
              )
            }
          >
            <n.icon width={19} height={19} />
            {n.label}
          </NavLink>
        ))}
        {/* Chat is tenant-scoped — Super Admins (no tenant) don't have a chat workspace.
            A Knowledge Base is mandatory: disable Open Chat until the tenant has one. */}
        {user?.role !== "super_admin" &&
          (chatAllowed === false ? (
            <div className="mt-2">
              <div
                aria-disabled
                className="flex cursor-not-allowed items-center gap-3 rounded-lg bg-slate-100 px-3 py-2.5 text-sm font-medium text-slate-400"
                title="Chat cannot be opened because no Knowledge Base is available for this tenant."
              >
                <Icon.Chat width={19} height={19} /> Open Chat
              </div>
              <p className="mt-1.5 px-1 text-[11px] leading-snug text-slate-400">
                Chat cannot be opened because no Knowledge Base is available for this tenant. Please
                create or upload a Knowledge Base first.
              </p>
            </div>
          ) : (
            <NavLink
              to="/chat"
              className="mt-2 flex items-center gap-3 rounded-lg bg-slate-900 px-3 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800"
            >
              <Icon.Chat width={19} height={19} /> Open Chat
            </NavLink>
          ))}
      </nav>
    </div>
  );

  return (
    <div className="flex h-full min-h-screen bg-slate-50">
      {/* Desktop sidebar */}
      <aside className="hidden w-64 flex-none border-r border-slate-200 bg-white lg:block">
        {SidebarContent}
      </aside>

      {/* Mobile drawer */}
      {drawer && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/40" onClick={() => setDrawer(false)} />
          <aside className="absolute left-0 top-0 h-full w-72 animate-fade-in-up bg-white shadow-pop">
            {SidebarContent}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Topbar */}
        <header className="sticky top-0 z-30 flex h-16 flex-none items-center justify-between gap-3 border-b border-slate-200 bg-white/90 px-4 backdrop-blur sm:px-6">
          <button className="btn-ghost rounded-lg p-2 lg:hidden" onClick={() => setDrawer(true)} aria-label="Open menu">
            <Icon.Menu />
          </button>
          <div className="flex-1" />
          <div className="relative">
            <button
              onClick={() => setMenu((m) => !m)}
              className="flex items-center gap-2 rounded-full py-1 pl-1 pr-2.5 transition hover:bg-slate-100"
            >
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-100 text-sm font-semibold text-brand-700">
                {initials(user?.name || "U")}
              </span>
              <span className="hidden text-left sm:block">
                <span className="block text-sm font-semibold leading-4 text-slate-800">{user?.name}</span>
                <span className="block text-[11px] text-slate-400">{roleLabel(user?.role)}</span>
              </span>
              <Icon.ChevronDown width={16} height={16} className="text-slate-400" />
            </button>
            {menu && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setMenu(false)} />
                <div className="absolute right-0 z-20 mt-2 w-56 animate-fade-in-up rounded-xl border border-slate-200 bg-white p-1.5 shadow-pop">
                  <div className="border-b border-slate-100 px-3 py-2">
                    <p className="truncate text-sm font-semibold text-slate-800">{user?.name}</p>
                    <p className="truncate text-xs text-slate-400">{user?.email}</p>
                  </div>
                  <button
                    onClick={() => {
                      setMenu(false);
                      navigate("/admin/profile");
                    }}
                    className="mt-1 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
                  >
                    <Icon.Settings width={17} height={17} /> Profile &amp; password
                  </button>
                  <button
                    onClick={async () => {
                      await logout();
                      navigate("/login");
                    }}
                    className="mt-1 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-rose-600 hover:bg-rose-50"
                  >
                    <Icon.Logout width={17} height={17} /> Sign out
                  </button>
                </div>
              </>
            )}
          </div>
        </header>

        <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-7xl">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
