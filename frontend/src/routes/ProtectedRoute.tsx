import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "@/context/AuthContext";
import { Spinner } from "@/components/ui/primitives";
import type { Role } from "@/api/types";

function FullscreenLoader() {
  return (
    <div className="flex h-screen items-center justify-center text-slate-400">
      <Spinner className="h-6 w-6" />
    </div>
  );
}

export function ProtectedRoute({ children, roles }: { children: ReactNode; roles?: Role[] }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <FullscreenLoader />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (roles && !roles.includes(user.role)) {
    // Chat users hitting an admin route go to chat; admins hitting a forbidden
    // admin sub-route go to the dashboard.
    return <Navigate to={user.role === "chat_user" ? "/chat" : "/admin"} replace />;
  }
  return <>{children}</>;
}
