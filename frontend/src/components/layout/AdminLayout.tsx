import { useState, type ReactNode } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { ChevronLeft, ChevronRight, X as CloseIcon, Plus } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { Icon } from "@/components/ui/Icons";
import { cn, initials, relativeTime, roleLabel } from "@/lib/utils";
import type { Role } from "@/api/types";
import logo from "@/assets/full-logo.png";
import iconLogo from "@/assets/icon-logo.png";
import { LoadingBlock, ErrorState } from "@/components/ui/primitives";
import { useChat } from "@/context/ChatContext";
import InputField from "../common/InputField";
import Button from "../ui/Button";

const SIDEBAR_GRADIENT = "bg-[linear-gradient(180deg,#6A5AF9_0%,#8364FF_100%)]";
const TOGGLE_GRADIENT = "bg-[linear-gradient(90deg,#5948E6_0%,#7354F0_100%)]";
const NAV_ACTIVE =
  "bg-[linear-gradient(90deg,#5948E6_0%,#7354F0_100%)] text-white font-semibold border border-[#7354F0] shadow-sm";
const NAV_IDLE =
  "bg-transparent text-white/90 border border-white/30 hover:text-white hover:bg-[linear-gradient(90deg,#5948E6_0%,#7354F0_100%)] hover:border-[#7354F0]";

interface NavItem {
  to: string;
  label: string;
  icon: (p: any) => ReactNode;
  roles?: Role[];
}
const ADMIN_NAV: NavItem[] = [
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

// ─── Brand header ───────────────────────────────────────────────────────────
function Brand({ mode, collapsed, onClose }: { mode: "admin" | "chat"; collapsed: boolean; onClose: () => void }) {
  return (
    <div
      className={cn(
        "flex items-center border-b border-white/15",
        collapsed ? "justify-center px-2 py-4" : "justify-between px-4 py-4",
      )}
    >
      <div className={cn("flex flex-col gap-2", collapsed ? "items-center" : "items-start")}>
        <img
          src={collapsed ? iconLogo : logo}
          alt="Logo"
          className={cn("w-auto object-contain", collapsed ? "h-8" : "h-12")}
        />
        {!collapsed && (
          <span className="text-[13px] font-semibold text-white/90 tracking-widest uppercase ml-0.5">
            {mode === "admin" ? "Admin Console" : "Chat Workspace"}
          </span>
        )}
      </div>
      {!collapsed && (
        <CloseIcon
          className="h-5 w-5 cursor-pointer text-white lg:hidden"
          onClick={onClose}
        />
      )}
    </div>
  );
}

function AdminSidebarContent({
  user,
  collapsed,
  onClose,
}: {
  user: any;
  collapsed: boolean;
  onClose: () => void;
}) {
  const visible = ADMIN_NAV.filter((n) => !n.roles || (user && n.roles.includes(user.role)));
  return (
    <div className={cn("flex h-full flex-col", SIDEBAR_GRADIENT)}>
      <Brand mode="admin" collapsed={collapsed} onClose={onClose} />
      <nav className={cn("flex-1 space-y-1.5 overflow-y-auto no-scrollbar", collapsed ? "px-2 py-4" : "px-3 py-3")}>
        {visible.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.to === "/admin"}
            onClick={onClose}
            title={collapsed ? n.label : ""}
            className={({ isActive }) =>
              cn(
                "group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition",
                collapsed ? "justify-center" : "",
                isActive ? NAV_ACTIVE : NAV_IDLE,
              )
            }
          >
            <n.icon width={18} height={18} className="shrink-0 transition-transform group-hover:scale-110" />
            {!collapsed && <span className="truncate">{n.label}</span>}
          </NavLink>
        ))}
        {user?.role !== "super_admin" && (
          <NavLink
            to="/chat"
            onClick={onClose}
            title={collapsed ? "Open Chat" : ""}
            className={cn(
              "mt-2 flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium border border-white text-white transition hover:bg-white hover:text-brand-700",
              collapsed ? "justify-center" : "",
            )}
          >
            <Icon.Chat width={18} height={18} className="shrink-0" />
            {!collapsed && "Open Chat"}
          </NavLink>
        )}
      </nav>
    </div>
  );
}

function ChatSidebarContent({ collapsed, onClose }: { collapsed: boolean; onClose: () => void }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const {
    sessions,
    loadingSessions,
    sessionsError,
    loadSessions,
    activeId,
    setActiveId,
    search,
    setSearch,
    creatingChat,
    startNewChat,
  } = useChat();
  const filtered = sessions.filter((s) =>
    (s.title || "").toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <div className={cn("flex h-full flex-col", SIDEBAR_GRADIENT)}>
      <Brand mode="chat" collapsed={collapsed} onClose={onClose} />

      {/* New chat button */}
      <div className={cn("pt-3 pb-2", collapsed ? "px-2" : "px-3")}>
        <Button
          variant="outline"
          className={cn(
            "bg-white w-full",
            collapsed ? "px-0" : "px-3",
          )}
          onClick={startNewChat}
          disabled={creatingChat}
          loading={creatingChat}
          title={collapsed ? "New Chat" : ""}
          leftIcon={<Plus className="w-4 h-4" />}
        >
          {!collapsed && "New Chat"}
        </Button>
      </div>

      {/* Search */}
      {!collapsed && (
        <div className="px-3 pb-3">
          <InputField
            name="search"
            type="search"
            value={search}
            placeholder="Search conversations"
            size="md"
            onChange={(_, value) => setSearch(value)}
            inputStyle="
      !bg-[#4E40C8]
      !border-[#6557DB]
      !text-white
      placeholder:!text-white/55
      focus:!ring-[#8E83FF]
      focus:!border-[#8E83FF]
      hover:!border-[#8E83FF]
      shadow-none
      rounded-xl
    "
            leftIcon={
              <Icon.Search
                width={16}
                height={16}
                className="text-white/60"
              />
            }
            rightIcon={
              search ? (
                <button
                  onClick={() => setSearch("")}
                  className="pointer-events-auto rounded-full p-0.5 hover:bg-white/10"
                >
                  <CloseIcon className="h-4 w-4 text-white/60 hover:text-white" />
                </button>
              ) : null
            }
          />
        </div>
      )}

      {/* Session list */}
      <div className={cn("min-h-0 flex-1 overflow-y-auto no-scrollbar pb-2", collapsed ? "px-1.5" : "px-2")}>
        {loadingSessions ? (
          <LoadingBlock label="Loading chats…" />
        ) : sessionsError ? (
          <ErrorState message={sessionsError} onRetry={loadSessions} />
        ) : filtered.length === 0 ? (
          !collapsed && (
            <p className="px-3 py-6 text-center text-sm text-white/60">No conversations yet.</p>
          )
        ) : (
          filtered.map((s) => (
            <button
              key={s.id}
              onClick={() => {
                setActiveId(s.id);
                onClose();
              }}
              title={collapsed ? s.title || "New Chat" : ""}
              className={cn(
                "group mb-1 flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left transition border",
                collapsed ? "justify-center" : "",
                activeId === s.id
                  ? "bg-[linear-gradient(90deg,#5948E6_0%,#7354F0_100%)] border-[#7354F0] text-white"
                  : "border-transparent text-white/90 hover:bg-white/10 hover:border-white/20",
              )}
            >
              <Icon.Chat width={15} height={15} className="flex-none text-white/70 group-hover:scale-110 transition-transform" />
              {!collapsed && (
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{s.title || "New Chat"}</span>
                  <span className="block text-[11px] text-white/60">{relativeTime(s.updated_at)}</span>
                </span>
              )}
            </button>
          ))
        )}
      </div>

      {/* Go to admin (for tenant_admin) */}
      {user?.role === "tenant_admin" && (
        <div className={cn("border-t border-white/15 pt-2 pb-3", collapsed ? "px-2" : "px-3")}>
          <button
            onClick={() => navigate("/admin")}
            title={collapsed ? "Admin Console" : ""}
            className={cn(
              "flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-white border border-white/30 transition hover:bg-white hover:text-brand-700",
              collapsed ? "justify-center" : "",
            )}
          >
            <Icon.Dashboard width={15} height={15} />
            {!collapsed && "Admin Console"}
          </button>
        </div>
      )}
    </div>
  );
}

// ─── Profile dropdown (shared) ───────────────────────────────────────────────
function ProfileMenu({
  mode,
  onChangePw,
}: {
  mode: "admin" | "chat";
  onChangePw?: () => void;
}) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 rounded-full py-1 pl-1 pr-2.5 transition hover:bg-white/15"
      >
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-white/20 text-sm font-semibold text-white">
          {initials(user?.name || "U")}
        </span>
        <span className="hidden text-left sm:block">
          <span className="block text-sm font-semibold leading-4 text-white">{user?.name}</span>
          <span className="block text-[11px] text-white/70">{roleLabel(user?.role)}</span>
        </span>
        <Icon.ChevronDown width={16} height={16} className="text-white/70" />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-20 mt-2 w-56 animate-fade-in-up rounded-xl border border-slate-200 bg-white p-1.5 shadow-pop">
            <div className="border-b border-slate-100 px-3 py-2">
              <p className="truncate text-sm font-semibold text-slate-800">{user?.name}</p>
              <p className="truncate text-xs text-slate-400">{user?.email}</p>
            </div>
            {mode === "admin" ? (
              <button
                onClick={() => {
                  setOpen(false);
                  navigate("/admin/profile");
                }}
                className="mt-1 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
              >
                <Icon.Settings width={17} height={17} /> Profile & password
              </button>
            ) : (
              onChangePw && (
                <button
                  onClick={() => {
                    setOpen(false);
                    onChangePw();
                  }}
                  className="mt-1 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
                >
                  <Icon.Settings width={17} height={17} /> Change password
                </button>
              )
            )}
            <button
              onClick={async () => {
                setOpen(false);
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
  );
}

// ─── AppLayout — the single unified layout shell ─────────────────────────────
interface AppLayoutProps {
  mode: "admin" | "chat";
  /** Topbar center/left content (e.g. chat title, breadcrumb). */
  topbarContent?: ReactNode;
  /** Callback to open "change password" modal (chat mode only). */
  onChangePw?: () => void;
  children: ReactNode;
}
export function AppLayout({ mode, topbarContent, onChangePw, children }: AppLayoutProps) {
  const { user } = useAuth();
  const [drawer, setDrawer] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  const SidebarContent = (isCollapsed: boolean, onClose: () => void) =>
    mode === "admin" ? (
      <AdminSidebarContent user={user} collapsed={isCollapsed} onClose={onClose} />
    ) : (
      <ChatSidebarContent collapsed={isCollapsed} onClose={onClose} />
    );

  const expandedWidth = mode === "admin" ? "lg:w-64" : "lg:w-72";
  const collapsedWidth = "lg:w-16";

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">
      {/* Desktop sidebar — fixed width, full height, never scrolls the page */}
      <aside
        className={cn(
          "relative hidden flex-none lg:flex lg:flex-col transition-all duration-300 ease-in-out",
          collapsed ? collapsedWidth : expandedWidth,
        )}
      >
        {SidebarContent(collapsed, () => setDrawer(false))}
        {/* Collapse toggle */}
        <button
          onClick={() => setCollapsed((c) => !c)}
          className={cn(
            "absolute -right-3 top-6 z-10 rounded-full p-1 text-white shadow-lg hover:shadow-xl transition",
            TOGGLE_GRADIENT,
          )}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </aside>

      {/* Mobile drawer overlay */}
      {drawer && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm"
            onClick={() => setDrawer(false)}
          />
          <aside
            className={cn(
              "absolute left-0 top-0 h-full w-72 animate-fade-in-up shadow-pop",
            )}
          >
            {SidebarContent(false, () => setDrawer(false))}
          </aside>
        </div>
      )}

      {/* Main column — fills remaining width, internally scrollable */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Topbar */}
        <header className="flex h-14 flex-none items-center gap-3 bg-[linear-gradient(90deg,#6A5AF9_0%,#8364FF_100%)] px-4 shadow-sm sm:px-6">
          <button
            className="rounded-lg p-2 text-white transition hover:bg-white/15 lg:hidden"
            onClick={() => setDrawer(true)}
            aria-label="Open menu"
          >
            <Icon.Menu />
          </button>
          <div className="min-w-0 flex-1 text-white">{topbarContent}</div>
          <ProfileMenu mode={mode} onChangePw={onChangePw} />
        </header>
        {/* Page content */}
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          {children}
        </div>
      </div>
    </div>
  );
}

// ─── Admin shell (wraps Outlet) ──────────────────────────────────────────────
export function AdminLayout() {
  return (
    <AppLayout mode="admin">
      <main className="h-full overflow-y-auto px-4 py-6 sm:px-6 lg:px-6">
        <div className="mx-auto max-w-7xl">
          <Outlet />
        </div>
      </main>
    </AppLayout>
  );
}