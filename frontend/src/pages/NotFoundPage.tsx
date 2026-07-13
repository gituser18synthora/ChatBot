import { Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

export function NotFoundPage() {
  const { user } = useAuth();
  const home = !user ? "/login" : user.role === "chat_user" ? "/chat" : "/admin";
  return (
    <div className="flex h-screen flex-col items-center justify-center px-6 text-center">
      <p className="text-6xl font-bold text-brand-600">404</p>
      <h1 className="mt-3 text-xl font-semibold text-slate-800">Page not found</h1>
      <p className="mt-1 max-w-sm text-sm text-slate-500">
        The page you're looking for doesn't exist or you don't have access to it.
      </p>
      <Link to={home} className="btn-primary mt-6">
        Go back
      </Link>
    </div>
  );
}
