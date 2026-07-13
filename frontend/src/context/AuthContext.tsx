import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { authApi } from "@/api/services";
import { tokenStore } from "@/api/client";
import type { Role, User } from "@/api/types";

interface AuthCtx {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  isAdmin: boolean;
  isSuperAdmin: boolean;
  hasRole: (...roles: Role[]) => boolean;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    (async () => {
      if (!tokenStore.access) {
        setLoading(false);
        return;
      }
      try {
        const me = await authApi.me();
        if (active) setUser(me);
      } catch {
        tokenStore.clear();
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const login = async (email: string, password: string) => {
    const u = await authApi.login(email, password);
    setUser(u);
    return u;
  };

  const logout = async () => {
    await authApi.logout();
    setUser(null);
  };

  const value: AuthCtx = {
    user,
    loading,
    login,
    logout,
    isAdmin: user?.role === "super_admin" || user?.role === "tenant_admin",
    isSuperAdmin: user?.role === "super_admin",
    hasRole: (...roles: Role[]) => !!user && roles.includes(user.role),
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
