import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { documentApi, kbApi } from "@/api/services";
import { useList } from "@/hooks/useList";
import { useToast } from "@/context/ToastContext";
import { useTenantScope, TenantPicker } from "@/components/common/TenantPicker";
import { PageHeader, SearchInput, EmptyState, ErrorState, Card } from "@/components/ui/primitives";
import { DataTable, Pagination, type Column } from "@/components/ui/DataTable";
import { ConfirmDialog } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Field";
import { DocStatusBadge } from "@/components/ui/StatusBadge";
import { Icon } from "@/components/ui/Icons";
import { Spinner } from "@/components/ui/primitives";
import { formatBytes, formatDate } from "@/lib/utils";
import type { DocumentItem, KnowledgeBase } from "@/api/types";

const STATUSES = ["", "pending", "uploading", "processing", "completed", "failed"];

// Sentinel for the "New Knowledge Base" choice (upload into a brand-new KB).
// "" is the neutral "Select Knowledge Base" placeholder; a real id selects an
// existing KB. Keeping them distinct lets "New Knowledge Base" sit at the end
// of the dropdown after the existing KBs.
const NEW_KB = "__new__";

export function DocumentsPage() {
  const toast = useToast();
  const scope = useTenantScope();
  const [params, setParams] = useSearchParams();
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [kbId, setKbId] = useState<string>(params.get("kb") || "");
  const [statusFilter, setStatusFilter] = useState("");
  const isNewKb = kbId === NEW_KB;
  // The id of a selected EXISTING KB (empty for the placeholder and New-KB mode).
  const realKbId = isNewKb ? "" : kbId;

  const loadKbs = () => {
    if (!scope.selected) {
      setKbs([]);
      setKbId("");
      return;
    }
    const requestedKb = params.get("kb") || "";
    kbApi.list(scope.selected, { per_page: 100 }).then((res) => {
      setKbs(res.items);
      setKbId((cur) => {
        if (cur && res.items.some((k) => k.id === cur)) return cur;
        if (requestedKb && res.items.some((k) => k.id === requestedKb)) return requestedKb;
        return "";
      });
    });
  };

  // When arriving from the KB page with ?tenant=, honor it (super admin).
  useEffect(() => {
    const t = params.get("tenant");
    if (t && scope.isSuperAdmin) scope.setSelected(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope.isSuperAdmin]);

  // Load KBs for the current tenant scope.
  useEffect(() => {
    loadKbs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope.selected]);

  const list = useList<DocumentItem>(
    (page, search) =>
      realKbId
        ? documentApi.list(realKbId, { page, search, status: statusFilter || undefined })
        : Promise.resolve({ items: [], meta: { page, per_page: 20, total: 0, pages: 0 } }),
    [realKbId, statusFilter],
  );

  const activeKb = useMemo(() => kbs.find((k) => k.id === realKbId), [kbs, realKbId]);
  // One document per Knowledge Base. Failed documents don't occupy the slot —
  // e.g. an upload that died because KMRAG was down must not surface the
  // "already contains its document" notice on top of the service error.
  // While a document is still uploading/processing the zone is disabled too,
  // but the only message shown is the KB's own status ("indexing is pending");
  // the "already contains its document" notice is reserved for a KB whose
  // document actually made it in (indexed).
  const kbOccupied =
    (activeKb?.document_count ?? 0) - (activeKb?.failed_count ?? 0) > 0;
  const kbIndexed = (activeKb?.indexed_count ?? 0) > 0;
  // Uploading is allowed for a New Knowledge Base, or an existing KB that is
  // active and still empty. The neutral placeholder ("" — nothing chosen) leaves
  // the drop zone disabled until the user picks New KB or an existing one.
  const uploadDisabled =
    !scope.selected ||
    (!kbId && !isNewKb) ||
    (!!realKbId && (activeKb?.status === "inactive" || kbOccupied));
  const refreshAfterUpload = (nextKbId?: string) => {
    if (nextKbId) {
      setKbId(nextKbId);
    }
    list.reload();
    loadKbs();
  };

  // Auto-refresh while any document is still ingesting so status flips to
  // Indexed/Failed without a manual refresh. Backend reconciles on each list
  // call. The poll is SILENT (rows stay on screen, no loading spinner — no
  // flicker) and stops on its own once no document is in flight.
  const hasPending = useMemo(
    () => list.items.some((d) => d.upload_status === "pending" || d.upload_status === "processing" || d.upload_status === "uploading"),
    [list.items],
  );
  useEffect(() => {
    if (!hasPending) return;
    const t = window.setInterval(() => list.reload({ silent: true }), 5000);
    return () => window.clearInterval(t);
  }, [hasPending, list.reload]);

  // The KB's status/message ("indexing is pending" -> "ready for chat") is
  // refreshed once, AFTER the poll sees the document reach a final status.
  // Refreshing it inside the poll raced the documents call (which is what
  // reconciles statuses server-side) and could stop polling with a stale
  // "Document indexing is pending." message until a manual page refresh.
  const prevPending = useRef(false);
  useEffect(() => {
    if (prevPending.current && !hasPending) loadKbs();
    prevPending.current = hasPending;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasPending]);

  return (
    <div>
      <PageHeader title="Documents" subtitle="Upload and manage documents for retrieval" />

      <Card className="p-4">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          {scope.isSuperAdmin && (
            <TenantPicker
              tenants={scope.tenants}
              value={scope.selected}
              onChange={(v) => {
                scope.setSelected(v);
                setParams({});
              }}
              className="w-full sm:w-48"
            />
          )}
          <Select
            value={kbId}
            onChange={(e) => {
              const v = e.target.value;
              setKbId(v);
              // Only an existing KB is reflected in the URL; the placeholder and
              // New-KB modes carry no ?kb param.
              const isReal = !!v && v !== NEW_KB;
              setParams(isReal ? { kb: v, ...(scope.isSuperAdmin && scope.selected ? { tenant: scope.selected } : {}) } : {});
            }}
            className="w-full sm:w-56"
          >
            <option value="">Select Knowledge Base</option>
            {kbs.map((k) => (
              <option key={k.id} value={k.id}>
                {k.kb_name}
              </option>
            ))}
            <option value={NEW_KB}>New Knowledge Base</option>
          </Select>
          {realKbId && (
            <>
              <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="w-full sm:w-40">
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s ? s[0].toUpperCase() + s.slice(1) : "All statuses"}
                  </option>
                ))}
              </Select>
              <SearchInput value={list.search} onChange={list.setSearch} placeholder="Search filename…" />
            </>
          )}
          <button
            className="btn-secondary ml-auto"
            onClick={() => {
              list.reload();
              loadKbs();
            }}
            title="Refresh status"
          >
            <Icon.Retry width={16} height={16} /> Refresh
          </button>
        </div>

        {scope.selected && !kbId && !isNewKb && (
              <p className="mb-2 text-xs text-slate-500">
                Select a Knowledge Base to view its document, or choose <b>New Knowledge Base</b> to
                upload a new file.
              </p>
            )}
            <UploadZone
              tenantId={scope.selected}
              kbId={realKbId}
              kbName={activeKb?.kb_name || ""}
              onUploaded={refreshAfterUpload}
              disabled={uploadDisabled}
            />
            {!!realKbId && kbIndexed && (
              <p className="mt-2 text-xs text-amber-600">
                This Knowledge Base already contains its document — each Knowledge Base holds
                exactly one. Switch to <b>New Knowledge Base</b> to upload another file, or delete
                the existing document to replace it.
              </p>
            )}
            {!!realKbId && activeKb?.status === "inactive" && (
              <p className="mt-2 text-xs text-amber-600">
                This knowledge base is inactive. Activate it to upload documents.
              </p>
            )}
            {!!realKbId && activeKb?.status_message && activeKb.status !== "inactive" && (
              <p className={`mt-2 text-xs ${activeKb.status === "failed" ? "text-rose-600" : activeKb.status === "ready" ? "text-emerald-600" : "text-amber-600"}`}>
                {activeKb.status_message}
              </p>
            )}
            <p className="mt-2 flex items-start gap-1.5 text-xs text-slate-400">
              <Icon.Book width={13} height={13} className="mt-0.5 flex-none" />
              After upload, documents are ingested in the background (
              <b className="font-medium text-slate-500">Processing</b>) and update automatically to{" "}
              <b className="font-medium text-emerald-600">Indexed</b> once ready, or{" "}
              <b className="font-medium text-rose-600">Failed</b> if ingestion doesn't complete.
            </p>
            {realKbId && (
              <div className="mt-4">
                {list.error ? (
                  <ErrorState message={list.error} onRetry={list.reload} />
                ) : (
                  <>
                    <DataTable
                      columns={buildColumns(toast, () => {
                        list.reload();
                        loadKbs();
                      })}
                      rows={list.items}
                      loading={list.loading}
                      empty={
                        <EmptyState icon={<Icon.Doc />} title="No documents yet" description="Drag and drop a file above to ingest it." />
                      }
                    />
                    <Pagination meta={list.meta} onPage={list.setPage} />
                  </>
                )}
              </div>
            )}
      </Card>
    </div>
  );
}

function buildColumns(toast: ReturnType<typeof useToast>, reload: () => void): Column<DocumentItem>[] {
  return [
    {
      header: "File",
      cell: (d) => (
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 flex-none items-center justify-center rounded-lg bg-slate-100 text-slate-500">
            <Icon.Doc width={18} height={18} />
          </span>
          <div className="min-w-0">
            <p className="truncate font-medium text-slate-900">{d.original_filename}</p>
            <p className="text-xs text-slate-400">{formatBytes(d.file_size_bytes)}</p>
          </div>
        </div>
      ),
    },
    {
      header: "Status",
      cell: (d) => (
        <div>
          <DocStatusBadge status={d.upload_status} />
          {d.ingestion_error && <p className="mt-1 max-w-xs truncate text-xs text-rose-500">{d.ingestion_error}</p>}
        </div>
      ),
    },
    { header: "Uploaded", hideOn: "md", cell: (d) => <span className="text-sm text-slate-500">{formatDate(d.uploaded_at || d.created_at)}</span> },
    {
      header: "",
      className: "text-right w-1",
      cell: (d) => <RowActions doc={d} toast={toast} reload={reload} />,
    },
  ];
}

function RowActions({ doc, toast, reload }: { doc: DocumentItem; toast: ReturnType<typeof useToast>; reload: () => void }) {
  const [confirm, setConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const retryRef = useRef<HTMLInputElement>(null);

  const onRetryPick = async (file?: File) => {
    if (!file) return;
    try {
      await documentApi.retry(doc.id, file);
      toast.success("Re-uploaded for processing.");
      reload();
    } catch (e: any) {
      toast.error(e.message);
    }
  };

  const remove = async () => {
    setDeleting(true);
    try {
      const res = await documentApi.remove(doc.id);
      toast.success(res?.note ? `${res.message} ${res.note}` : "Document removed.");
      setConfirm(false);
      reload();
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="flex justify-end gap-1">
      {(doc.upload_status === "failed" || doc.upload_status === "pending") && (
        <>
          <input
            ref={retryRef}
            type="file"
            className="hidden"
            onChange={(e) => onRetryPick(e.target.files?.[0])}
          />
          <button className="btn-secondary px-2.5 py-1.5 text-xs" onClick={() => retryRef.current?.click()}>
            <Icon.Retry width={15} height={15} /> Retry
          </button>
        </>
      )}
      <button className="btn-ghost rounded-lg p-2 text-rose-500 hover:bg-rose-50" onClick={() => setConfirm(true)} aria-label="Delete">
        <Icon.Trash width={17} height={17} />
      </button>
      <ConfirmDialog
        open={confirm}
        onClose={() => setConfirm(false)}
        onConfirm={remove}
        loading={deleting}
        danger
        title="Remove document"
        confirmLabel="Remove"
        message={
          <span>
            Remove <b>{doc.original_filename}</b> from this knowledge base? It will no longer appear
            here. Vector data is retained in the RAG engine until a KMRAG delete endpoint exists.
          </span>
        }
      />
    </div>
  );
}

function UploadZone({
  tenantId,
  kbId,
  kbName,
  onUploaded,
  disabled,
}: {
  tenantId: string;
  kbId: string;
  kbName: string;
  onUploaded: (kbId?: string) => void;
  disabled?: boolean;
}) {
  const toast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploads, setUploads] = useState<{ id: string; name: string; pct: number; error?: string }[]>([]);
  const seq = useRef(0);

  const handleFiles = async (files: FileList | null) => {
    if (!files || files.length === 0 || disabled) return;
    if (!tenantId) {
      toast.error("Select a tenant before uploading.");
      return;
    }
    // One document per Knowledge Base: uploading into a selected KB is only
    // allowed while it is empty, so never accept more than one file for it.
    if (kbId && files.length > 1) {
      toast.error("A Knowledge Base holds exactly one document. Upload one file at a time.");
      return;
    }
    for (const file of Array.from(files)) {
      const id = `u${++seq.current}`;
      setUploads((u) => [...u, { id, name: file.name, pct: 0 }]);
      try {
        const result = kbId
          ? {
              document: await documentApi.upload(kbId, file, (pct) =>
                setUploads((u) => u.map((x) => (x.id === id ? { ...x, pct } : x))),
              ),
            }
          : await documentApi.createKbAndUpload(tenantId, file, undefined, (pct) =>
              setUploads((u) => u.map((x) => (x.id === id ? { ...x, pct } : x))),
            );
        toast.success(
          kbId
            ? `"${file.name}" queued for processing.`
            : `"${file.name}" queued in its own new Knowledge Base.`,
        );
        setUploads((u) => u.filter((x) => x.id !== id));
        onUploaded(result.document.kb_id);
      } catch (e: any) {
        setUploads((u) => u.map((x) => (x.id === id ? { ...x, error: e.message } : x)));
        toast.error(e.message);
        onUploaded();
      }
    }
    // Allow re-selecting the same file again.
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => e.key === "Enter" && !disabled && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handleFiles(e.dataTransfer.files);
        }}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-8 text-center transition ${
          disabled
            ? "cursor-not-allowed border-slate-200 bg-slate-50 opacity-60"
            : dragging
              ? "border-brand-500 bg-brand-50"
              : "border-slate-300 bg-slate-50/50 hover:border-brand-400 hover:bg-brand-50/40"
        }`}
      >
        <span className="mb-2 flex h-11 w-11 items-center justify-center rounded-full bg-brand-100 text-brand-600">
          <Icon.Upload />
        </span>
        <p className="text-sm font-medium text-slate-700">
          Drop files here or <span className="text-brand-600">browse</span>
        </p>
        <p className="mt-1 text-xs text-slate-400">
          PDF, DOCX, TXT, CSV, XLSX, images ·{" "}
          {kbId ? (
            <>
              uploads to <b>{kbName || "selected Knowledge Base"}</b> (one document per Knowledge Base)
            </>
          ) : (
            <b>each file is stored in its own new Knowledge Base</b>
          )}
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple={!kbId}
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>
      {uploads.length > 0 && (
        <div className="mt-3 space-y-2">
          {uploads.map((u) => (
            <div key={u.id} className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm">
              {u.error ? (
                <Icon.Warning className="text-rose-500" width={16} height={16} />
              ) : (
                <Spinner className="text-brand-500" />
              )}
              <span className="min-w-0 flex-1 truncate text-slate-700">{u.name}</span>
              {u.error ? (
                <span className="text-xs text-rose-500">{u.error}</span>
              ) : (
                <div className="flex items-center gap-2">
                  <div className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-200">
                    <div className="h-full rounded-full bg-brand-500 transition-all" style={{ width: `${u.pct}%` }} />
                  </div>
                  <span className="w-9 text-right text-xs text-slate-400">{u.pct}%</span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
