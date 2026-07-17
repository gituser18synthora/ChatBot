import { FormEvent, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { Spinner } from "@/components/ui/primitives";
import { Icon } from "@/components/ui/Icons";
import RobotImage from "@/assets/synthora-ai-front-view.png";
import AurexionLogo from "@/assets/Aurexion-logo.svg";
import InputField from "@/components/common/InputField";

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
      toast.success(`Welcome back, ${u.name}`);
      navigate(u.role === "chat_user" ? "/chat" : "/admin", { replace: true });
    } catch (err: any) {
      setError(err?.message || "Unable to sign in.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-slate-50">
      {/* Brand panel — robot art on a gradient, rounded cut like Aurexion's */}
      <div className="hidden lg:block w-1/2">
        <div className="relative w-full h-full flex flex-col justify-between items-end overflow-hidden bg-gradient-to-br from-brand-700 via-brand-600 to-brand-800 p-12">
          <div className="flex items-center justify-end w-full">
            <img src={AurexionLogo} alt="Aurexion" className="h-14 w-auto object-contain brightness-0 invert" />
          </div>

          <img
            src={RobotImage}
            alt="Robot"
            className="absolute bottom-0 left-0 h-[85%] w-auto object-contain opacity-95"
          />

          <div className="relative z-10 max-w-sm mb-6">
            <h1 className="text-3xl font-bold leading-tight text-white">
              Grounded AI answers from your organization's knowledge.
            </h1>
            <p className="mt-3 text-brand-50 text-sm">
              Multi-tenant chat, document-aware retrieval, and full usage &amp; cost analytics — in one secure console.
            </p>
          </div>

          <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-white/10 blur-2xl" />
        </div>
      </div>

      {/* Form */}
      <div className="w-full lg:w-1/2 flex items-center justify-center p-6 ">
        <div className="w-full max-w-md rounded-3xl p-[1.6px] bg-gradient-to-br from-brand-200 via-brand-400 to-brand-200">
          <div className="bg-white rounded-3xl px-8 py-10 flex flex-col gap-8">
            <div className="flex justify-between items-center">
              <div className="flex items-center justify-between w-full">
                <h2 className="text-2xl font-semibold text-slate-900 text-start">Sign in</h2>
                <h2 className="text-2xl font-semibold text-primary text-start">AI Chatbot</h2>
              </div>
            </div>
            <form onSubmit={onSubmit} className="space-y-4">
              {error && (
                <div className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2.5 text-sm text-rose-700">
                  <Icon.Warning width={18} height={18} className="mt-0.5 flex-none" />
                  <span>{error}</span>
                </div>
              )}

              <InputField
                label="Email"
                name="email"
                type="email"
                value={email}
                onChange={(name, value) => setEmail(value)}
                placeholder="you@company.com"
              />
              <InputField
                label="Password"
                type="password"
                name="password"
                value={password}
                onChange={(name, value) => setPassword(value)}
                placeholder="••••••••"
              />

              <button type="submit" className="btn-primary w-full !rounded-full mt-2" disabled={submitting}>
                {submitting && <Spinner className="text-white" />}
                Sign in
              </button>
              <p className="mt-6 text-center text-xs text-slate-400">
                Protected workspace. Contact your administrator for access.
              </p>
            </form>

          </div>
        </div>
      </div>
    </div>
  );
}