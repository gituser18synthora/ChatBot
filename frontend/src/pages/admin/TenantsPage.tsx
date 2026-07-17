import { FormEvent, useState } from "react";
import { tenantApi } from "@/api/services";
import { useList } from "@/hooks/useList";
import { useToast } from "@/context/ToastContext";
import { PageHeader, SearchInput, EmptyState, ErrorState, Card } from "@/components/ui/primitives";
import { DataTable, Pagination, type Column } from "@/components/ui/DataTable";
import { Modal, ConfirmDialog } from "@/components/ui/Modal";
import { Field, TextInput, Select } from "@/components/ui/Field";
import { ActiveBadge } from "@/components/ui/StatusBadge";
import { Icon } from "@/components/ui/Icons";
import { Spinner } from "@/components/ui/primitives";
import { formatDate } from "@/lib/utils";
import type { Tenant } from "@/api/types";

export function TenantsPage() {
  const toast = useToast();
  const list = useList<Tenant>((page, search) => tenantApi.list({ page, search }));
  const [editing, setEditing] = useState<Tenant | null>(null);
  const [creating, setCreating] = useState(false);
  const [toDelete, setToDelete] = useState<Tenant | null>(null);
  const [deleting, setDeleting] = useState(false);

  const remove = async () => {
    if (!toDelete) return;
    setDeleting(true);
    try {
      await tenantApi.remove(toDelete.id);
      toast.success("Tenant deleted.");
      setToDelete(null);
      list.reload();
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setDeleting(false);
    }
  };

  const columns: Column<Tenant>[] = [
    {
      header: "Tenant",
      cell: (t) => (
        <div>
          <div className="flex items-center gap-2">
            <p className="font-medium text-slate-900">{t.tenant_name}</p>
          </div>
          <p className="text-xs text-slate-400">{t.tenant_code}</p>
        </div>
      ),
    },
    { header: "Status", cell: (t) => <ActiveBadge status={t.status} /> },
    {
      header: "Contact",
      hideOn: "md",
      cell: (t) => (
        <div className="text-sm">
          <p className="text-slate-700">{t.contact_name || "—"}</p>
          <p className="text-xs text-slate-400">{t.contact_email || ""}</p>
        </div>
      ),
    },
    { header: "Created", hideOn: "sm", cell: (t) => <span className="text-sm text-slate-500">{formatDate(t.created_at)}</span> },
    {
      header: "",
      className: "text-right w-1",
      cell: (t) => (
        <div className="flex justify-end gap-1">
          <button className="btn-ghost rounded-lg p-2" onClick={() => setEditing(t)} aria-label="Edit">
            <Icon.Edit width={17} height={17} />
          </button>
          <button className="btn-ghost rounded-lg p-2 text-rose-500 hover:bg-rose-50" onClick={() => setToDelete(t)} aria-label="Delete">
            <Icon.Trash width={17} height={17} />
          </button>
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Tenants"
        subtitle="Organizations using the platform"
        actions={
          <button className="btn-primary" onClick={() => setCreating(true)}>
            <Icon.Plus width={16} height={16} /> New Tenant
          </button>
        }
      />

      <Card className="p-4">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <SearchInput value={list.search} onChange={list.setSearch} placeholder="Search tenants…" />
          <span className="ml-auto text-sm text-slate-400">{list.meta?.total ?? 0} total</span>
        </div>
        {list.error ? (
          <ErrorState message={list.error} onRetry={list.reload} />
        ) : (
          <>
            <DataTable
              columns={columns}
              rows={list.items}
              loading={list.loading}
              empty={
                <EmptyState
                  icon={<Icon.Building />}
                  title="No tenants yet"
                  description="Create your first tenant to start onboarding knowledge bases and users."
                  action={
                    <button className="btn-primary" onClick={() => setCreating(true)}>
                      <Icon.Plus width={16} height={16} /> New Tenant
                    </button>
                  }
                />
              }
            />
            <Pagination meta={list.meta} onPage={list.setPage} />
          </>
        )}
      </Card>

      {(creating || editing) && (
        <TenantModal
          tenant={editing}
          onClose={() => {
            setCreating(false);
            setEditing(null);
          }}
          onSaved={() => {
            setCreating(false);
            setEditing(null);
            list.reload();
          }}
        />
      )}

      <ConfirmDialog
        open={!!toDelete}
        onClose={() => setToDelete(null)}
        onConfirm={remove}
        loading={deleting}
        danger
        title="Delete tenant"
        confirmLabel="Delete tenant"
        message={
          <span>
            <b>{toDelete?.tenant_name}</b> will be archived (soft-deleted): it is removed from the
            active list and its users can no longer sign in, but all data is retained for audit and
            future reference. It is not permanently erased.
          </span>
        }
      />
    </div>
  );
}

function TenantModal({
  tenant,
  onClose,
  onSaved,
}: {
  tenant: Tenant | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const isEdit = !!tenant;
  const [form, setForm] = useState({
    tenant_name: tenant?.tenant_name || "",
    tenant_code: tenant?.tenant_code || "",
    status: tenant?.status || "active",
    rag_mode: tenant?.rag_mode || "rag_first",
    contact_name: tenant?.contact_name || "",
    contact_email: tenant?.contact_email || "",
    admin_name: "",
    admin_email: "",
    admin_password: "",
  });
  const [saving, setSaving] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (isEdit) {
        await tenantApi.update(tenant!.id, {
          tenant_name: form.tenant_name,
          status: form.status as Tenant["status"],
          rag_mode: form.rag_mode as Tenant["rag_mode"],
          contact_name: form.contact_name || null,
          contact_email: form.contact_email || null,
        });
        toast.success("Tenant updated.");
      } else {
        // Tenants are always created as normal tenants. The single Super Tenant
        // (owner of the shared KB library) is designated later via Edit.
        const created = await tenantApi.create({
          tenant_name: form.tenant_name,
          status: form.status as Tenant["status"],
          contact_name: form.contact_name || null,
          contact_email: form.contact_email || null,
          admin_name: form.admin_name || form.contact_name || undefined,
          admin_email: form.admin_email,
          admin_password: form.admin_password,
        });
        toast.success(
          created.admin
            ? `Tenant created. Login: ${created.admin.email}`
            : "Tenant created.",
        );
      }
      onSaved();
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title={isEdit ? "Edit tenant" : "New tenant"}
      footer={
        <>
          <button className="btn-secondary" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button className="btn-primary" form="tenant-form" disabled={saving}>
            {saving && <Spinner className="text-white" />}
            {isEdit ? "Save changes" : "Create tenant"}
          </button>
        </>
      }
    >
      <form id="tenant-form" onSubmit={submit} autoComplete="off" className="space-y-4">
        {!isEdit && (
          <div aria-hidden="true" className="pointer-events-none absolute -left-[10000px] top-auto h-0 w-0 overflow-hidden opacity-0">
            <input tabIndex={-1} type="text" name="tenant-autofill-decoy-user" autoComplete="username" />
            <input tabIndex={-1} type="password" name="tenant-autofill-decoy-password" autoComplete="current-password" />
          </div>
        )}
        <Field label="Tenant name" required>
          <TextInput
            required
            name="tenant-name"
            autoComplete="organization"
            value={form.tenant_name}
            onChange={(e) => setForm({ ...form, tenant_name: e.target.value })}
          />
        </Field>
        {isEdit ? (
          <Field label="Tenant code" hint="Generated by the system and cannot be changed.">
            <TextInput disabled value={form.tenant_code} readOnly />
          </Field>
        ) : (
          <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">
            A unique tenant code is generated automatically from the tenant name.
          </p>
        )}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Contact name">
            <TextInput
              name="tenant-contact-name"
              autoComplete="off"
              value={form.contact_name}
              onChange={(e) => setForm({ ...form, contact_name: e.target.value })}
            />
          </Field>
          <Field label="Contact email">
            <TextInput
              type="email"
              name="tenant-contact-email"
              autoComplete="email"
              value={form.contact_email}
              onChange={(e) => setForm({ ...form, contact_email: e.target.value })}
            />
          </Field>
        </div>
        <Field label="Status">
          <Select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as Tenant["status"] })}>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </Select>
        </Field>
        {isEdit && (
          <Field
            label="Chatbot answering mode"
            hint={
              form.rag_mode === "rag_only"
                ? "Answers come only from the tenant's Knowledge Bases. General AI is disabled."
                : "Document questions are answered from Knowledge Bases; clearly general questions may use general AI."
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
        )}
        {!isEdit && (
          <div className="space-y-4 rounded-lg border border-slate-200 bg-slate-50/60 p-3">
            <div>
              <p className="text-sm font-semibold text-slate-700">Tenant login</p>
              <p className="text-xs text-slate-400">
                A Tenant Admin account is created so this tenant can sign in and manage their own
                users, knowledge bases, and documents.
              </p>
            </div>
            <Field label="Admin name">
              <TextInput
                name="new-tenant-admin-name"
                autoComplete="off"
                value={form.admin_name}
                placeholder="Defaults to the contact name"
                onChange={(e) => setForm({ ...form, admin_name: e.target.value })}
              />
            </Field>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Admin email" required>
                <TextInput
                  type="email"
                  required
                  name="new-tenant-admin-email"
                  autoComplete="off"
                  data-lpignore="true"
                  data-1p-ignore="true"
                  value={form.admin_email}
                  onChange={(e) => setForm({ ...form, admin_email: e.target.value })}
                />
              </Field>
              <Field label="Temporary password" required hint="At least 8 characters.">
                <TextInput
                  type="password"
                  required
                  minLength={8}
                  name="new-tenant-temporary-password"
                  autoComplete="new-password"
                  data-lpignore="true"
                  data-1p-ignore="true"
                  spellCheck={false}
                  value={form.admin_password}
                  onChange={(e) => setForm({ ...form, admin_password: e.target.value })}
                />
              </Field>
            </div>
          </div>
        )}
      </form>
    </Modal>
  );
}
