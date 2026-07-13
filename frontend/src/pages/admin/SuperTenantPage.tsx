import { useState } from "react";
import { superTenantApi, tenantApi, type ShareableKb } from "@/api/services";
import { useList } from "@/hooks/useList";
import { useAsync } from "@/hooks/useAsync";
import { useToast } from "@/context/ToastContext";
import { PageHeader, SearchInput, EmptyState, ErrorState, Card, Badge, LoadingBlock } from "@/components/ui/primitives";
import { Modal, ConfirmDialog } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Field";
import { Spinner } from "@/components/ui/primitives";
import { Icon } from "@/components/ui/Icons";
import type { Tenant } from "@/api/types";

export function SuperTenantPage() {
  const info = useAsync(() => superTenantApi.info(), []);
  const list = useList<ShareableKb>((page, search) => superTenantApi.shareableKbs({ page, search }));
  const [managing, setManaging] = useState<ShareableKb | null>(null);

  if (info.loading) return <LoadingBlock label="Loading Super Tenant…" />;

  const superTenant = info.data?.super_tenant;

  return (
    <div>
      <PageHeader
        title="Super Tenant"
        subtitle="Share the central knowledge base library with tenants"
      />

      {!superTenant ? (
        <EmptyState
          icon={<Icon.Building />}
          title="No Super Tenant configured"
          description="Designate one tenant as the Super Tenant (edit a tenant and enable “Super Tenant”). Its knowledge bases become the shared library you can assign to other tenants."
        />
      ) : (
        <>
          <Card className="mb-4 flex items-center gap-3 p-4">
            <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-violet-50 text-violet-600">
              <Icon.Building width={20} height={20} />
            </span>
            <div>
              <p className="text-sm font-semibold text-slate-900">{superTenant.tenant_name}</p>
              <p className="text-xs text-slate-400">
                Super Tenant · owns the shared KB library · code {superTenant.tenant_code}
              </p>
            </div>
            <Badge tone="purple">Super Tenant</Badge>
          </Card>

          <Card className="p-4">
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <SearchInput value={list.search} onChange={list.setSearch} placeholder="Search knowledge bases…" />
              <span className="ml-auto text-sm text-slate-400">{list.meta?.total ?? 0} knowledge bases</span>
            </div>
            {list.error ? (
              <ErrorState message={list.error} onRetry={list.reload} />
            ) : list.loading ? (
              <LoadingBlock />
            ) : list.items.length === 0 ? (
              <EmptyState
                icon={<Icon.Book />}
                title="No shareable knowledge bases"
                description="Create knowledge bases under the Super Tenant, then assign them to tenants here."
              />
            ) : (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                {list.items.map((kb) => (
                  <div key={kb.id} className="rounded-xl border border-slate-200 p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate font-semibold text-slate-900">{kb.kb_name}</p>
                        <p className="text-xs text-slate-400">{kb.document_count ?? 0} documents</p>
                      </div>
                      <button className="btn-secondary px-2.5 py-1.5 text-xs" onClick={() => setManaging(kb)}>
                        <Icon.Users width={14} height={14} /> Manage access
                      </button>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {kb.assigned_tenants.length === 0 ? (
                        <span className="text-xs text-slate-400">Not shared with any tenant yet.</span>
                      ) : (
                        kb.assigned_tenants.map((a) => (
                          <Badge key={a.tenant_id} tone="blue">
                            {a.tenant_name || a.tenant_id.slice(0, 8)}
                          </Badge>
                        ))
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </>
      )}

      {managing && (
        <ManageAccessModal
          kb={managing}
          superTenantId={superTenant!.id}
          onClose={() => setManaging(null)}
          onChanged={() => {
            list.reload();
          }}
        />
      )}
    </div>
  );
}

function ManageAccessModal({
  kb,
  superTenantId,
  onClose,
  onChanged,
}: {
  kb: ShareableKb;
  superTenantId: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const toast = useToast();
  const tenants = useAsync(() => tenantApi.list({ per_page: 100 }), []);
  const assigned = useAsync(() => superTenantApi.shareableKbs({ per_page: 100 }), []);
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState(false);
  const [toRevoke, setToRevoke] = useState<string | null>(null);

  // Current assignments for this KB (fresh from the list).
  const current = (assigned.data?.items.find((k) => k.id === kb.id)?.assigned_tenants ?? kb.assigned_tenants);
  const assignedIds = new Set(current.map((a) => a.tenant_id));
  const candidates = (tenants.data?.items ?? []).filter(
    (t: Tenant) => t.id !== superTenantId && !assignedIds.has(t.id),
  );

  const assign = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      await superTenantApi.assign(kb.id, selected);
      toast.success("Knowledge base shared with tenant.");
      setSelected("");
      await assigned.reload();
      onChanged();
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  const revoke = async () => {
    if (!toRevoke) return;
    setBusy(true);
    try {
      await superTenantApi.unassign(kb.id, toRevoke);
      toast.success("Access revoked.");
      setToRevoke(null);
      await assigned.reload();
      onChanged();
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open onClose={onClose} title={`Share “${kb.kb_name}”`} size="md">
      <div className="space-y-4">
        <div>
          <p className="label">Grant access to a tenant</p>
          <div className="flex gap-2">
            <Select value={selected} onChange={(e) => setSelected(e.target.value)} className="flex-1">
              <option value="">Select a tenant…</option>
              {candidates.map((t: Tenant) => (
                <option key={t.id} value={t.id}>
                  {t.tenant_name}
                </option>
              ))}
            </Select>
            <button className="btn-primary" onClick={assign} disabled={!selected || busy}>
              {busy ? <Spinner className="text-white" /> : <Icon.Plus width={16} height={16} />} Assign
            </button>
          </div>
        </div>

        <div>
          <p className="label">Tenants with access</p>
          {current.length === 0 ? (
            <p className="rounded-lg bg-slate-50 px-3 py-3 text-sm text-slate-500">
              Not shared with any tenant yet.
            </p>
          ) : (
            <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
              {current.map((a) => (
                <li key={a.tenant_id} className="flex items-center justify-between px-3 py-2.5">
                  <span className="text-sm text-slate-700">{a.tenant_name || a.tenant_id}</span>
                  <button
                    className="btn-ghost rounded-lg p-1.5 text-rose-500 hover:bg-rose-50"
                    onClick={() => setToRevoke(a.tenant_id)}
                    aria-label="Revoke"
                  >
                    <Icon.Trash width={16} height={16} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={!!toRevoke}
        onClose={() => setToRevoke(null)}
        onConfirm={revoke}
        loading={busy}
        danger
        title="Revoke access"
        confirmLabel="Revoke"
        message="The tenant's users will no longer be able to select or query this knowledge base."
      />
    </Modal>
  );
}
