import { useEffect, useState } from "react";
import { voiceApi } from "@/api/services";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { useVoiceSettings } from "@/context/VoiceSettingsContext";
import { VoiceSettingsForm } from "@/components/admin/VoiceSettingsForm";
import { PageHeader, Card, LoadingBlock } from "@/components/ui/primitives";
import { RoleBadge } from "@/components/ui/StatusBadge";
import { Icon } from "@/components/ui/Icons";
import { roleLabel } from "@/lib/utils";
import type { AdminVoiceSettings } from "@/api/types";

function VoiceSettingsCard() {
  const { user } = useAuth();
  const toast = useToast();
  const { refresh } = useVoiceSettings();
  const isSuper = user?.role === "super_admin";
  const [settings, setSettings] = useState<AdminVoiceSettings | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    (isSuper ? voiceApi.getPlatform() : voiceApi.getTenant())
      .then(setSettings)
      .catch((e: any) => setError(e.message));
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSuper]);

  if (error) return <p className="text-sm text-rose-600">{error}</p>;
  if (!settings) return <LoadingBlock label="Loading voice settings…" />;

  const save = async (body: Partial<AdminVoiceSettings>) => {
    try {
      const updated = isSuper ? await voiceApi.updatePlatform(body) : await voiceApi.updateTenant(body);
      setSettings(updated);
      await refresh(); // new playback uses the change immediately — no reload
      toast.success("Voice settings saved.");
    } catch (e: any) {
      toast.error(e.message);
    }
  };

  const reset = async () => {
    try {
      setSettings(await voiceApi.resetTenant());
      await refresh();
      toast.success("Voice settings reset to platform defaults.");
    } catch (e: any) {
      toast.error(e.message);
    }
  };

  return (
    <VoiceSettingsForm
      key={settings.updated_at || "initial"}
      initial={settings}
      showOverrideToggle={isSuper}
      locked={!isSuper && !settings.allow_tenant_override}
      onSave={save}
      onReset={isSuper ? undefined : reset}
    />
  );
}

export function SettingsPage() {
  const { user } = useAuth();

  return (
    <div>
      <PageHeader title="Settings" subtitle="Your profile and platform information" />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <h3 className="mb-4 text-sm font-semibold text-slate-800">Profile</h3>
          <dl className="space-y-3 text-sm">
            <Row label="Name" value={user?.name || "—"} />
            <Row label="Email" value={user?.email || "—"} />
            <Row label="Role" value={<RoleBadge role={user?.role || ""} />} />
            <Row label="Account" value={user?.is_active ? "Active" : "Disabled"} />
          </dl>
          <p className="mt-4 text-xs text-slate-400">
            To change your password, ask an administrator to update your account.
          </p>
        </Card>

        <Card className="p-5">
          <h3 className="mb-4 text-sm font-semibold text-slate-800">How answers work</h3>
          <ul className="space-y-3 text-sm text-slate-600">
            <li className="flex gap-2.5">
              <Icon.Book className="mt-0.5 flex-none text-brand-600" width={18} height={18} />
              <span>
                <b>Knowledge Base answers</b> are grounded in your uploaded documents and always show
                their sources.
              </span>
            </li>
            <li className="flex gap-2.5">
              <Icon.Sparkle className="mt-0.5 flex-none text-slate-500" width={18} height={18} />
              <span>
                <b>General AI answers</b> use the language model directly for questions that don't
                depend on your documents.
              </span>
            </li>
            <li className="flex gap-2.5">
              <Icon.Warning className="mt-0.5 flex-none text-amber-500" width={18} height={18} />
              <span>
                When no supporting document is found, the assistant says so instead of guessing.
              </span>
            </li>
          </ul>
        </Card>

        <Card className="p-5 lg:col-span-2">
          <h3 className="mb-1 text-sm font-semibold text-slate-800">
            Voice & audio {user?.role === "super_admin" ? "(platform defaults)" : "(your tenant)"}
          </h3>
          <p className="mb-4 text-xs text-slate-500">
            {user?.role === "super_admin"
              ? "System-wide text-to-speech defaults for every tenant. Turning off tenant overrides makes these settings final."
              : "Text-to-speech settings for your tenant's chat users. Unsaved tenants follow the platform defaults."}
          </p>
          <VoiceSettingsCard />
        </Card>

        <Card className="p-5 lg:col-span-2">
          <h3 className="mb-2 text-sm font-semibold text-slate-800">Document processing note</h3>
          <p className="text-sm text-slate-600">
            Uploaded documents are processed asynchronously by the retrieval engine. They remain in a{" "}
            <b>Processing</b> state after upload; there is currently no completion callback, so status
            reflects the last confirmed state. Deleting a document removes it from this console, but
            vector data is retained by the engine until a delete endpoint is available.
          </p>
        </Card>
      </div>

      <p className="mt-6 text-center text-xs text-slate-400">
        Aurexion Chatbot Platform · signed in as {roleLabel(user?.role)}
      </p>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-slate-500">{label}</dt>
      <dd className="font-medium text-slate-800">{value}</dd>
    </div>
  );
}
