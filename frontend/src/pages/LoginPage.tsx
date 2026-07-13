import { FormEvent, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { Field, TextInput } from "@/components/ui/Field";
import { Spinner } from "@/components/ui/primitives";
import { Icon } from "@/components/ui/Icons";

export function LoginPage() {
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (params.get("expired")) setError("Your session has expired. Please log in again.");
  }, [params]);

  useEffect(() => {
    if (user) navigate(user.role === "chat_user" ? "/chat" : "/admin", { replace: true });
  }, [user, navigate]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const u = await login(email.trim(), password);
      toast.success(`Welcome back, ${u.name.split(" ")[0]}`);
      navigate(u.role === "chat_user" ? "/chat" : "/admin", { replace: true });
    } catch (err: any) {
      setError(err?.message || "Unable to sign in.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen">
      {/* Brand panel */}
      <div className="relative hidden w-1/2 flex-col justify-between overflow-hidden bg-gradient-to-br from-brand-700 via-brand-600 to-brand-800 p-12 text-white lg:flex">
        <div className="flex items-center gap-2.5">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/15 backdrop-blur">
            <Icon.Sparkle />
          </div>
          <span className="text-lg font-bold">Aurexion</span>
        </div>
        <div>
          <h1 className="max-w-md text-4xl font-bold leading-tight">
            Grounded AI answers from your organization's knowledge.
          </h1>
          <p className="mt-4 max-w-md text-brand-100">
            Multi-tenant chat, document-aware retrieval, and full usage &amp; cost analytics — in one
            secure console.
          </p>
        </div>
        <div className="flex gap-6 text-sm text-brand-100">
          <span>Tenant isolation</span>
          <span>Source citations</span>
          <span>Cost tracking</span>
        </div>
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-white/10 blur-2xl" />
        <div className="pointer-events-none absolute -bottom-16 right-16 h-56 w-56 rounded-full bg-brand-400/20 blur-2xl" />
      </div>

      {/* Form */}
      <div className="flex w-full items-center justify-center px-6 lg:w-1/2">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-2.5 lg:hidden">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-600 text-white">
              <Icon.Sparkle />
            </div>
            <span className="text-lg font-bold text-slate-900">Aurexion</span>
          </div>
          <h2 className="text-2xl font-bold text-slate-900">Sign in</h2>
          <p className="mt-1 text-sm text-slate-500">Access your admin console or chat workspace.</p>

          <form onSubmit={onSubmit} className="mt-8 space-y-4">
            {error && (
              <div className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2.5 text-sm text-rose-700">
                <Icon.Warning width={18} height={18} className="mt-0.5 flex-none" />
                <span>{error}</span>
              </div>
            )}
            <Field label="Email" required>
              <TextInput
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
              />
            </Field>
            <Field label="Password" required>
              <TextInput
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
              />
            </Field>
            <button type="submit" className="btn-primary w-full" disabled={submitting}>
              {submitting && <Spinner className="text-white" />}
              Sign in
            </button>
          </form>
          <p className="mt-6 text-center text-xs text-slate-400">
            Protected workspace. Contact your administrator for access.
          </p>
        </div>
      </div>
    </div>
  );
}
