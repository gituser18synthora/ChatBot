import { FormEvent, useEffect, useState } from "react";
import { profileApi } from "@/api/services";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { ChangePasswordModal } from "@/components/common/ChangePasswordModal";
import { PageHeader, Card, Spinner, LoadingBlock, ErrorState } from "@/components/ui/primitives";
import { Field, TextInput, Select } from "@/components/ui/Field";
import { RoleBadge, ActiveBadge } from "@/components/ui/StatusBadge";
import type { Profile, Tenant } from "@/api/types";

export function ProfilePage() {
  const { user } = useAuth();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [changingPw, setChangingPw] = useState(false);

  const load = () => {
    setLoading(true);
    setError(null);
    profileApi
      .get()
      .then(setProfile)
      .catch((e: any) => setError(e.message))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const isTenantAdmin = user?.role === "tenant_admin";

  return (
    <div>
      <PageHeader title="Profile" subtitle="Your account and organization details" />

      {loading ? (
        <LoadingBlock label="Loading profile…" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* Account */}
          <Card className="p-5">
            <h3 className="mb-4 text-sm font-semibold text-slate-800">Account</h3>
            <dl className="space-y-3 text-sm">
              <div className="flex justify-between gap-4">
                <dt className="text-slate-400">Name</dt>
                <dd className="font-medium text-slate-800">{profile?.user.name}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-slate-400">Email</dt>
                <dd className="font-medium text-slate-800">{profile?.user.email}</dd>
              </div>
              <div className="flex items-center justify-between gap-4">
                <dt className="text-slate-400">Role</dt>
                <dd>{profile && <RoleBadge role={profile.user.role} />}</dd>
              </div>
            </dl>
            <div className="mt-5 border-t border-slate-100 pt-4">
              <button className="btn-secondary" onClick={() => setChangingPw(true)}>
                Change password
              </button>
            </div>
          </Card>

          {/* Tenant */}
          {profile?.tenant &&
            (isTenantAdmin ? (
              <TenantProfileForm tenant={profile.tenant} onSaved={load} />
            ) : (
              <ReadOnlyTenant tenant={profile.tenant} />
            ))}
        </div>
      )}

      {changingPw && <ChangePasswordModal onClose={() => setChangingPw(false)} />}
    </div>
  );
}

function TenantProfileForm({ tenant, onSaved }: { tenant: Tenant; onSaved: () => void }) {
  const toast = useToast();
  const [form, setForm] = useState({
    tenant_name: tenant.tenant_name,
    contact_name: tenant.contact_name || "",
    contact_email: tenant.contact_email || "",
    rag_mode: tenant.rag_mode || "rag_first",
  });
  const [saving, setSaving] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await profileApi.updateTenant({
        tenant_name: form.tenant_name,
        contact_name: form.contact_name || null,
        contact_email: form.contact_email || null,
        rag_mode: form.rag_mode as Tenant["rag_mode"],
      });
      toast.success("Organization profile updated.");
      onSaved();
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="p-5">
      <h3 className="mb-4 text-sm font-semibold text-slate-800">Organization</h3>
      <form onSubmit={submit} className="space-y-4">
        <Field label="Organization name" required>
          <TextInput required value={form.tenant_name} onChange={(e) => setForm({ ...form, tenant_name: e.target.value })} />
        </Field>
        <Field label="Tenant code" hint="Assigned by the platform and cannot be changed.">
          <TextInput disabled readOnly value={tenant.tenant_code} />
        </Field>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Contact name">
            <TextInput value={form.contact_name} onChange={(e) => setForm({ ...form, contact_name: e.target.value })} />
          </Field>
          <Field label="Contact email">
            <TextInput type="email" value={form.contact_email} onChange={(e) => setForm({ ...form, contact_email: e.target.value })} />
          </Field>
        </div>
        <Field
          label="Chatbot answering mode"
          hint={
            form.rag_mode === "rag_only"
              ? "The assistant answers only from your Knowledge Bases. Questions it cannot answer from documents get a clear \"not found\" reply."
              : "Document questions are answered from your Knowledge Bases; clearly general questions (e.g. coding help) may be answered by general AI."
          }
        >
          <Select
            value={form.rag_mode}
            onChange={(e) => setForm({ ...form, rag_mode: e.target.value as NonNullable<Tenant["rag_mode"]> })}
          >
            <option value="rag_first">RAG-first (general AI fallback allowed)</option>
            <option value="rag_only">RAG-only (Knowledge Base answers only)</option>
          </Select>
        </Field>
        <div className="flex justify-end pt-1">
          <button className="btn-primary" disabled={saving}>
            {saving && <Spinner className="text-white" />}
            Save changes
          </button>
        </div>
      </form>
    </Card>
  );
}

function ReadOnlyTenant({ tenant }: { tenant: Tenant }) {
  return (
    <Card className="p-5">
      <h3 className="mb-4 text-sm font-semibold text-slate-800">Organization</h3>
      <dl className="space-y-3 text-sm">
        <div className="flex justify-between gap-4">
          <dt className="text-slate-400">Name</dt>
          <dd className="font-medium text-slate-800">{tenant.tenant_name}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-slate-400">Tenant code</dt>
          <dd className="font-medium text-slate-800">{tenant.tenant_code}</dd>
        </div>
        <div className="flex items-center justify-between gap-4">
          <dt className="text-slate-400">Status</dt>
          <dd>
            <ActiveBadge status={tenant.status} />
          </dd>
        </div>
      </dl>
    </Card>
  );
}
