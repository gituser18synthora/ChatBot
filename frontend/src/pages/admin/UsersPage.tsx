import { FormEvent, useEffect, useState } from "react";
import { kbApi, userApi } from "@/api/services";
import { useList } from "@/hooks/useList";
import { useToast } from "@/context/ToastContext";
import { useAuth } from "@/context/AuthContext";
import { useTenantScope, TenantPicker } from "@/components/common/TenantPicker";
import { PageHeader, SearchInput, EmptyState, ErrorState, Card } from "@/components/ui/primitives";
import { DataTable, Pagination, type Column } from "@/components/ui/DataTable";
import { Modal, ConfirmDialog } from "@/components/ui/Modal";
import { Field, TextInput, Select } from "@/components/ui/Field";
import { RoleBadge } from "@/components/ui/StatusBadge";
import { Badge, Spinner } from "@/components/ui/primitives";
import { Icon } from "@/components/ui/Icons";
import { cn, formatDate } from "@/lib/utils";
import type { Role, SelectableKb, User } from "@/api/types";
import { ShieldBan } from "lucide-react";
import InputField from "@/components/common/InputField";

export function UsersPage() {
  const toast = useToast();
  const { user: me, isSuperAdmin } = useAuth();
  const scope = useTenantScope(true);
  const [roleFilter, setRoleFilter] = useState("");
  const list = useList<User>(
    (page, search) =>
      userApi.list({
        page,
        search,
        role: roleFilter || undefined,
        tenant_id: isSuperAdmin ? scope.selected || undefined : undefined,
      }),
    [scope.selected, roleFilter],
  );
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [scoping, setScoping] = useState<User | null>(null);
  const [toDelete, setToDelete] = useState<User | null>(null);
  const [deleting, setDeleting] = useState(false);

  const toggleStatus = async (u: User) => {
    try {
      await userApi.setStatus(u.id, !u.is_active);
      toast.success(u.is_active ? "User deactivated." : "User activated.");
      list.reload();
    } catch (e: any) {
      toast.error(e.message);
    }
  };

  // Super Users may delete anyone (but themselves); Tenant Admins only Chat Users.
  const canDelete = (u: User) =>
    u.id !== me?.id && (isSuperAdmin || u.role === "chat_user");

  const remove = async () => {
    if (!toDelete) return;
    setDeleting(true);
    try {
      await userApi.remove(toDelete.id);
      toast.success("User deleted. The record is retained for audit.");
      setToDelete(null);
      list.reload();
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setDeleting(false);
    }
  };

  const columns: Column<User>[] = [
    {
      header: "User",
      cell: (u) => (
        <div>
          <p className="font-medium text-slate-900">{u.name}</p>
          <p className="text-xs text-slate-400">{u.email}</p>
        </div>
      ),
    },
    { header: "Role", cell: (u) => <RoleBadge role={u.role} /> },
    {
      header: "Status",
      cell: (u) =>
        u.is_active ? <Badge tone="green">Active</Badge> : <Badge tone="gray">Disabled</Badge>,
    },
    { header: "Last login", hideOn: "md", cell: (u) => <span className="text-sm text-slate-500">{formatDate(u.last_login_at)}</span> },
    {
      header: "Actions",
      className: "text-left w-1",
      cell: (u) => (
        <div className="flex justify-end gap-1">
          {/* KB assignment is a Chat User concept: admins always use all tenant KBs. */}
          {u.role === "chat_user" && u.tenant_id && (
            <button
              className="btn-ghost rounded-lg p-2"
              onClick={() => setScoping(u)}
              aria-label="Knowledge base access"
              title="Knowledge base access"
            >
              <Icon.Book width={17} height={17} />
            </button>
          )}
          <button className="btn-ghost rounded-lg p-2" onClick={() => setEditing(u)} aria-label="Edit">
            <Icon.Edit width={17} height={17} />
          </button>
          <button
            className="btn-ghost rounded-lg p-2"
            disabled={u.id === me?.id}
            onClick={() => toggleStatus(u)}
            aria-label={u.is_active ? "Disable" : "Enable"}
            title={u.is_active ? "Disable" : "Enable"}
          >
            <ShieldBan className="text-rose-500" width={17} height={17} />
          </button>
          {canDelete(u) && (
            <button
              className="btn-ghost rounded-lg p-2 text-rose-500 hover:bg-rose-50"
              onClick={() => setToDelete(u)}
              aria-label="Delete"
            >
              <Icon.Trash width={17} height={17} />
            </button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Users"
        subtitle="Admins and chat users"
        actions={
          <button className="btn-primary" onClick={() => setCreating(true)}>
            <Icon.Plus width={16} height={16} /> New User
          </button>
        }
      />

      <Card className="p-4">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <SearchInput value={list.search} onChange={list.setSearch} placeholder="Search users…" />
          {isSuperAdmin && (
            <TenantPicker tenants={scope.tenants} value={scope.selected} onChange={scope.setSelected} allowAll className="w-full sm:w-48" />
          )}
          <Select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)} className="w-full sm:w-44">
            <option value="">All roles</option>
            {isSuperAdmin && <option value="super_admin">Super User</option>}
            <option value="tenant_admin">Tenant Admin</option>
            <option value="chat_user">Chat User</option>
          </Select>
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
              empty={<EmptyState icon={<Icon.Users />} title="No users found" description="Create a user to grant access." />}
            />
            <Pagination meta={list.meta} onPage={list.setPage} />
          </>
        )}
      </Card>

      {(creating || editing) && (
        <UserModal
          user={editing}
          tenants={scope.tenants}
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

      {scoping && (
        <UserKbModal user={scoping} onClose={() => setScoping(null)} />
      )}

      <ConfirmDialog
        open={!!toDelete}
        onClose={() => setToDelete(null)}
        onConfirm={remove}
        loading={deleting}
        danger
        title="Delete user"
        confirmLabel="Delete user"
        message={
          <span>
            <b>{toDelete?.name}</b> will be deleted (soft-deleted): they can no longer sign in and
            are removed from this list, but the record is retained for audit. This is not a permanent
            erase.
          </span>
        }
      />
    </div>
  );
}

function UserModal({
  user,
  tenants,
  onClose,
  onSaved,
}: {
  user: User | null;
  tenants: { id: string; tenant_name: string }[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const { isSuperAdmin, user: me } = useAuth();
  const isEdit = !!user;
  const [form, setForm] = useState({
    name: user?.name || "",
    email: user?.email || "",
    password: "",
    role: (user?.role || "chat_user") as Role,
    tenant_id: user?.tenant_id || (isSuperAdmin ? tenants[0]?.id || "" : me?.tenant_id || ""),
  });
  const [saving, setSaving] = useState(false);

  const needsTenant = form.role !== "super_admin";
  const isChatUserRole = form.role === "chat_user";

  // Initial KB scoping (create only — edit uses the dedicated access modal).
  // Applies to Chat Users only: no selection means the Chat User searches all
  // tenant knowledge bases automatically. Other roles always use all KBs.
  const [kbs, setKbs] = useState<SelectableKb[]>([]);
  const [kbIds, setKbIds] = useState<string[]>([]);
  const [loadingKbs, setLoadingKbs] = useState(false);
  useEffect(() => {
    if (isEdit || !isChatUserRole || !form.tenant_id) {
      setKbs([]);
      setKbIds([]);
      return;
    }
    let ok = true;
    setLoadingKbs(true);
    kbApi
      .selectable(form.tenant_id)
      .then((res) => {
        if (!ok) return;
        setKbs(res);
        setKbIds([]); // reset when the tenant changes
      })
      .catch(() => ok && setKbs([]))
      .finally(() => ok && setLoadingKbs(false));
    return () => {
      ok = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isEdit, isChatUserRole, form.tenant_id]);

  const toggleKb = (id: string) =>
    setKbIds((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  // A Chat User needs a Knowledge Base to query — block creation for a tenant
  // that has none yet. (kbs is only loaded for the create-Chat-User case.)
  const noKbForChatUser =
    !isEdit && isChatUserRole && !!form.tenant_id && !loadingKbs && kbs.length === 0;
  const NO_KB_MESSAGE =
    "A chat user cannot be created because this tenant does not have any Knowledge Base. Please create a Knowledge Base first.";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (noKbForChatUser) {
      toast.error(NO_KB_MESSAGE);
      return;
    }
    setSaving(true);
    try {
      if (isEdit) {
        await userApi.update(user!.id, {
          name: form.name,
          ...(form.password ? { password: form.password } : {}),
          ...(isSuperAdmin ? { role: form.role } : {}),
        });
        toast.success("User updated.");
      } else {
        await userApi.create({
          name: form.name,
          email: form.email,
          password: form.password,
          role: form.role,
          tenant_id: form.role === "super_admin" ? null : form.tenant_id,
          kb_ids: isChatUserRole ? kbIds : [],
        });
        toast.success(
          kbIds.length
            ? `User created with access to ${kbIds.length} knowledge base${kbIds.length > 1 ? "s" : ""}.`
            : "User created.",
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
      open={true}
      onClose={onClose}
      title={isEdit ? "Edit User" : "New User"}
      footer={
        <>
          <button className="btn-secondary" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button className="btn-primary" form="user-form" disabled={saving || noKbForChatUser}>
            {saving && <Spinner className="text-white" />}
            {isEdit ? "Save changes" : "Create User"}
          </button>
        </>
      }
    >
      <form id="user-form" onSubmit={submit} className="space-y-4">
        <Field label="Full name" required>
          <TextInput required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </Field>
        <Field label="Email" required>
          <TextInput type="email" required disabled={isEdit} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </Field>
        <Field label={isEdit ? "New password" : "Password"} required={!isEdit} hint={isEdit ? "Leave blank to keep current password." : "At least 8 characters."}>
          <InputField
            name="password"
            type="password"
            value={form.password}
            required={!isEdit}
            min={8}
            placeholder="Enter password"
            onChange={(name, value) =>
              setForm((prev) => ({
                ...prev,
                [name]: value,
              }))
            }
          />
        </Field>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Role" hint={!isSuperAdmin ? "Tenant Admins can only create Chat Users." : undefined}>
            <Select
              value={form.role}
              disabled={isEdit && !isSuperAdmin}
              onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
            >
              {isSuperAdmin && <option value="super_admin">Super User</option>}
              {/* Only a Super User may create Tenant Admins. */}
              {isSuperAdmin && <option value="tenant_admin">Tenant Admin</option>}
              <option value="chat_user">Chat User</option>
            </Select>
          </Field>
          {isSuperAdmin && needsTenant && !isEdit && (
            <Field label="Tenant" required>
              <Select value={form.tenant_id} onChange={(e) => setForm({ ...form, tenant_id: e.target.value })} required>
                {tenants.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.tenant_name}
                  </option>
                ))}
              </Select>
            </Field>
          )}
        </div>

        {/* Initial Knowledge Base access (create only; edit via the book icon).
            Chat Users only — every other role always uses all tenant KBs. */}
        {!isEdit && isChatUserRole && (
          <div>
            <p className="label">Knowledge base access</p>
            <p className="mb-2 text-xs text-slate-400">
              Optionally restrict this Chat User to specific knowledge bases. Select none to let
              them search all tenant knowledge bases automatically.
              {" "}Pending or failed Knowledge Bases can be assigned, but they are not usable in chat until indexing is ready.
              {" "}You can change this later from the user's{" "}
              <Icon.Book width={11} height={11} className="inline" /> access button.
            </p>
            {loadingKbs ? (
              <div className="flex items-center gap-2 py-3 text-sm text-slate-400">
                <Spinner /> Loading knowledge bases…
              </div>
            ) : kbs.length === 0 ? (
              <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm text-amber-700">
                {NO_KB_MESSAGE}
              </p>
            ) : (
              <>
                <div className="grid max-h-44 grid-cols-1 gap-2 overflow-y-auto sm:grid-cols-2">
                  {kbs.map((kb) => {
                    const on = kbIds.includes(kb.id);
                    return (
                      <button
                        key={kb.id}
                        type="button"
                        onClick={() => toggleKb(kb.id)}
                        className={cn(
                          "flex items-center gap-2.5 rounded-lg border px-3 py-2 text-left text-sm transition",
                          on ? "border-brand-500 bg-brand-50 text-brand-800" : "border-slate-200 hover:border-slate-300",
                        )}
                      >
                        <span
                          className={cn(
                            "flex h-5 w-5 flex-none items-center justify-center rounded border",
                            on ? "border-brand-600 bg-brand-600 text-white" : "border-slate-300",
                          )}
                        >
                          {on && <Icon.Check width={14} height={14} />}
                        </span>
                        <span className="min-w-0 flex-1 truncate">{kb.kb_name}</span>
                        {kb.ready === false && kb.status && (
                          <span className={cn(
                            "flex-none rounded px-1.5 py-0.5 text-[10px] font-semibold",
                            kb.status === "failed" ? "bg-rose-100 text-rose-700" : "bg-amber-100 text-amber-700",
                          )}>
                            {kb.status}
                          </span>
                        )}
                        {kb.shared && (
                          <span className="flex-none rounded bg-violet-100 px-1.5 py-0.5 text-[10px] font-semibold text-violet-700">
                            Shared
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
                <div className="mt-2">
                  {kbIds.length > 0 ? (
                    <Badge tone="blue">
                      Scoped to {kbIds.length} knowledge base{kbIds.length > 1 ? "s" : ""}
                    </Badge>
                  ) : (
                    <Badge tone="gray">Uses all tenant knowledge bases</Badge>
                  )}
                </div>
              </>
            )}
          </div>
        )}
      </form>
    </Modal>
  );
}

// Assign a specific set of Knowledge Bases to a Chat User (only Chat Users can
// be scoped). No selection means the Chat User searches all tenant KBs
// automatically.
function UserKbModal({ user, onClose }: { user: User; onClose: () => void }) {
  const toast = useToast();
  const [available, setAvailable] = useState<SelectableKb[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let ok = true;
    userApi
      .getKbs(user.id)
      .then((res) => {
        if (!ok) return;
        setAvailable(res.available);
        setSelected(res.assigned_kb_ids);
      })
      .catch((e: any) => ok && toast.error(e.message))
      .finally(() => ok && setLoading(false));
    return () => {
      ok = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user.id]);

  const toggle = (id: string) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const save = async () => {
    setSaving(true);
    try {
      await userApi.setKbs(user.id, selected);
      toast.success(
        selected.length
          ? `${user.name} is now scoped to ${selected.length} knowledge base${selected.length > 1 ? "s" : ""}.`
          : `${user.name} will search all tenant knowledge bases automatically.`,
      );
      onClose();
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title={`Knowledge base access — ${user.name}`}
      footer={
        <>
          <button className="btn-secondary" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button className="btn-primary" onClick={save} disabled={saving || loading}>
            {saving && <Spinner className="text-white" />}
            Save access
          </button>
        </>
      }
    >
      <div className="space-y-3">
        <p className="text-sm text-slate-500">
          Optionally restrict this Chat User to specific knowledge bases. Select none to let them
          search all tenant knowledge bases automatically.
          {" "}Pending or failed Knowledge Bases can be assigned, but they are not usable in chat until indexing is ready.
        </p>
        {loading ? (
          <div className="flex items-center gap-2 py-6 text-sm text-slate-400">
            <Spinner /> Loading knowledge bases…
          </div>
        ) : available.length === 0 ? (
          <p className="rounded-lg bg-slate-50 px-3 py-3 text-sm text-slate-500">
            This tenant has no knowledge bases yet. The Chat User will automatically use any tenant
            knowledge bases created later.
          </p>
        ) : (
          <>
            <div className="grid max-h-64 grid-cols-1 gap-2 overflow-y-auto sm:grid-cols-2">
              {available.map((kb) => {
                const on = selected.includes(kb.id);
                return (
                  <button
                    key={kb.id}
                    type="button"
                    onClick={() => toggle(kb.id)}
                    className={cn(
                      "flex items-center gap-2.5 rounded-lg border px-3 py-2.5 text-left text-sm transition",
                      on ? "border-brand-500 bg-brand-50 text-brand-800" : "border-slate-200 hover:border-slate-300",
                    )}
                  >
                    <span
                      className={cn(
                        "flex h-5 w-5 flex-none items-center justify-center rounded border",
                        on ? "border-brand-600 bg-brand-600 text-white" : "border-slate-300",
                      )}
                    >
                      {on && <Icon.Check width={14} height={14} />}
                    </span>
                    <span className="min-w-0 flex-1 truncate">{kb.kb_name}</span>
                    {kb.ready === false && kb.status && (
                      <span className={cn(
                        "flex-none rounded px-1.5 py-0.5 text-[10px] font-semibold",
                        kb.status === "failed" ? "bg-rose-100 text-rose-700" : "bg-amber-100 text-amber-700",
                      )}>
                        {kb.status}
                      </span>
                    )}
                    {kb.shared && (
                      <span className="flex-none rounded bg-violet-100 px-1.5 py-0.5 text-[10px] font-semibold text-violet-700">
                        Shared
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
            <div>
              {selected.length > 0 ? (
                <Badge tone="blue">
                  Scoped to {selected.length} knowledge base{selected.length > 1 ? "s" : ""}
                </Badge>
              ) : (
                <Badge tone="gray">Uses all tenant knowledge bases</Badge>
              )}
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
