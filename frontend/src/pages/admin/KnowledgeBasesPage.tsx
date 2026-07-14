import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { kbApi } from "@/api/services";
import { useList } from "@/hooks/useList";
import { useToast } from "@/context/ToastContext";
import { useTenantScope, TenantPicker } from "@/components/common/TenantPicker";
import { PageHeader, SearchInput, EmptyState, ErrorState, Card, Badge } from "@/components/ui/primitives";
import { DataTable, Pagination, type Column } from "@/components/ui/DataTable";
import { Modal, ConfirmDialog } from "@/components/ui/Modal";
import { Field, TextInput, TextArea, Select } from "@/components/ui/Field";
import { KBStatusBadge } from "@/components/ui/StatusBadge";
import { Icon } from "@/components/ui/Icons";
import { Spinner } from "@/components/ui/primitives";
import { formatDate } from "@/lib/utils";
import type { KnowledgeBase } from "@/api/types";

export function KnowledgeBasesPage() {
  const toast = useToast();
  const navigate = useNavigate();
  const scope = useTenantScope();
  const list = useList<KnowledgeBase>(
    (page, search) => kbApi.list(scope.selected, { page, search }),
    [scope.selected],
  );
  const [editing, setEditing] = useState<KnowledgeBase | null>(null);
  const [creating, setCreating] = useState(false);
  const [toDelete, setToDelete] = useState<KnowledgeBase | null>(null);
  const [deleting, setDeleting] = useState(false);

  // A KB that still holds documents cannot be deleted (backend returns 409
  // KB_HAS_DOCUMENTS). Reflect that in the confirm dialog before the call.
  const deleteBlocked = (toDelete?.document_count ?? 0) > 0;

  const remove = async () => {
    if (!toDelete || deleteBlocked) return;
    setDeleting(true);
    try {
      await kbApi.remove(toDelete.id);
      toast.success("Knowledge base deleted.");
      setToDelete(null);
      list.reload();
    } catch (e: any) {
      // Backend guards this too; surface its explanation (e.g. KB_HAS_DOCUMENTS).
      toast.error(e.message);
      list.reload();
    } finally {
      setDeleting(false);
    }
  };

  const columns: Column<KnowledgeBase>[] = [
    {
      header: "Knowledge Base",
      cell: (kb) => (
        <div>
          <p className="font-medium text-slate-900">{kb.kb_name}</p>
          {kb.description && <p className="max-w-xs truncate text-xs text-slate-400">{kb.description}</p>}
        </div>
      ),
    },
    {
      header: "Documents",
      cell: (kb) => (
        <div className="flex flex-wrap gap-1">
          <Badge tone="blue">{kb.document_count ?? 0} docs</Badge>
          {(kb.indexed_count ?? 0) > 0 && <Badge tone="green">{kb.indexed_count} indexed</Badge>}
          {(kb.processing_count ?? 0) > 0 && <Badge tone="amber">{kb.processing_count} pending</Badge>}
          {(kb.failed_count ?? 0) > 0 && <Badge tone="red">{kb.failed_count} failed</Badge>}
        </div>
      ),
    },
    {
      header: "Status",
      cell: (kb) => (
        <div>
          <KBStatusBadge status={kb.status} />
          {kb.status_message && <p className="mt-1 max-w-xs truncate text-xs text-slate-400">{kb.status_message}</p>}
        </div>
      ),
    },
    { header: "Created", hideOn: "md", cell: (kb) => <span className="text-sm text-slate-500">{formatDate(kb.created_at)}</span> },
    {
      header: "",
      className: "text-right w-1",
      cell: (kb) => (
        <div className="flex justify-end gap-1">
          <button
            className="btn-secondary px-2.5 py-1.5 text-xs"
            onClick={() => navigate(`/admin/documents?kb=${kb.id}&tenant=${kb.tenant_id}`)}
          >
            <Icon.Doc width={15} height={15} /> Docs
          </button>
          <button className="btn-ghost rounded-lg p-2" onClick={() => setEditing(kb)} aria-label="Edit">
            <Icon.Edit width={17} height={17} />
          </button>
          <button className="btn-ghost rounded-lg p-2 text-rose-500 hover:bg-rose-50" onClick={() => setToDelete(kb)} aria-label="Delete">
            <Icon.Trash width={17} height={17} />
          </button>
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Knowledge Bases"
        subtitle="Document collections used to ground answers"
        actions={
          <button className="btn-primary" onClick={() => setCreating(true)} disabled={!scope.selected}>
            <Icon.Plus width={16} height={16} /> New Knowledge Base
          </button>
        }
      />

      <Card className="p-4">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          {scope.isSuperAdmin && (
            <TenantPicker tenants={scope.tenants} value={scope.selected} onChange={scope.setSelected} className="w-full sm:w-56" />
          )}
          <SearchInput value={list.search} onChange={list.setSearch} placeholder="Search knowledge bases…" />
          <span className="ml-auto text-sm text-slate-400">{list.meta?.total ?? 0} total</span>
        </div>

        {scope.isSuperAdmin && !scope.selected ? (
          <EmptyState icon={<Icon.Building />} title="Select a tenant" description="Choose a tenant to view its knowledge bases." />
        ) : list.error ? (
          <ErrorState message={list.error} onRetry={list.reload} />
        ) : (
          <>
            <DataTable
              columns={columns}
              rows={list.items}
              loading={list.loading}
              empty={
                <EmptyState
                  icon={<Icon.Book />}
                  title="No knowledge bases"
                  description="Create a knowledge base, then upload documents to make them searchable."
                  action={
                    <button className="btn-primary" onClick={() => setCreating(true)}>
                      <Icon.Plus width={16} height={16} /> New Knowledge Base
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
        <KBModal
          kb={editing}
          tenantId={scope.selected}
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
        title="Delete knowledge base"
        confirmLabel="Delete"
        confirmDisabled={deleteBlocked}
        message={
          deleteBlocked ? (
            <span>
              This knowledge base contains documents and cannot be deleted. Delete or move all
              documents first.
            </span>
          ) : (
            <span>
              Delete <b>{toDelete?.kb_name}</b>? Its document records will be removed from the
              console. Note: vector data in the RAG engine is retained until a KMRAG delete endpoint
              is available.
            </span>
          )
        }
      />
    </div>
  );
}

function KBModal({
  kb,
  tenantId,
  onClose,
  onSaved,
}: {
  kb: KnowledgeBase | null;
  tenantId: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const isEdit = !!kb;
  const [form, setForm] = useState({
    kb_name: kb?.kb_name || "",
    description: kb?.description || "",
    availability: kb?.status === "inactive" ? "inactive" : "enabled",
  });
  const [saving, setSaving] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (isEdit) {
        await kbApi.update(kb!.id, {
          kb_name: form.kb_name,
          description: form.description || null,
          status: form.availability === "inactive" ? "inactive" : "ready",
        });
        toast.success("Knowledge base updated.");
      } else {
        await kbApi.create(tenantId, { kb_name: form.kb_name, description: form.description || null });
        toast.success("Knowledge base created. Upload documents to start indexing.");
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
      title={isEdit ? "Edit knowledge base" : "New knowledge base"}
      footer={
        <>
          <button className="btn-secondary" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button className="btn-primary" form="kb-form" disabled={saving}>
            {saving && <Spinner className="text-white" />}
            {isEdit ? "Save changes" : "Create"}
          </button>
        </>
      }
    >
      <form id="kb-form" onSubmit={submit} className="space-y-4">
        <Field label="Name" required>
          <TextInput required value={form.kb_name} onChange={(e) => setForm({ ...form, kb_name: e.target.value })} placeholder="e.g. Product Manuals" />
        </Field>
        <Field label="Description">
          <TextArea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="What this knowledge base contains…" />
        </Field>
        <Field
          label="Availability"
          hint="Readiness is automatic. Disable a knowledge base to hide it from assignments and chat."
        >
          <Select value={form.availability} onChange={(e) => setForm({ ...form, availability: e.target.value })}>
            <option value="enabled">Enabled</option>
            <option value="inactive">Inactive</option>
          </Select>
        </Field>
      </form>
    </Modal>
  );
}
