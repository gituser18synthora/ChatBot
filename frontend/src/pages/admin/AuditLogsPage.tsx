import { useState } from "react";
import { auditApi } from "@/api/services";
import { useList } from "@/hooks/useList";
import { useAuth } from "@/context/AuthContext";
import { useTenantScope, TenantPicker } from "@/components/common/TenantPicker";
import { PageHeader, EmptyState, ErrorState, Card, Badge } from "@/components/ui/primitives";
import { DataTable, Pagination, type Column } from "@/components/ui/DataTable";
import { Select } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { Icon } from "@/components/ui/Icons";
import { formatDate, titleCase } from "@/lib/utils";
import type { AuditLog } from "@/api/types";

const ACTIONS = [
  "",
  "login",
  "logout",
  "tenant_created",
  "tenant_updated",
  "tenant_deleted",
  "user_created",
  "user_updated",
  "kb_created",
  "kb_updated",
  "kb_deleted",
  "document_uploaded",
  "document_deleted",
  "chat_session_created",
  "chat_session_deleted",
];

function actionTone(action: string): "green" | "red" | "blue" | "amber" | "gray" {
  if (action.includes("deleted") || action.includes("disabled")) return "red";
  if (action.includes("created")) return "green";
  if (action.includes("updated")) return "blue";
  if (action === "login" || action === "logout") return "gray";
  return "amber";
}

export function AuditLogsPage() {
  const { isSuperAdmin } = useAuth();
  const scope = useTenantScope(true);
  const [action, setAction] = useState("");
  const list = useList<AuditLog>(
    (page) =>
      auditApi.list({
        page,
        action: action || undefined,
        tenant_id: isSuperAdmin ? scope.selected || undefined : undefined,
      }),
    [scope.selected, action],
  );
  const [detail, setDetail] = useState<AuditLog | null>(null);

  const columns: Column<AuditLog>[] = [
    { header: "Action", cell: (a) => <Badge tone={actionTone(a.action)}>{titleCase(a.action)}</Badge> },
    {
      header: "Entity",
      hideOn: "sm",
      cell: (a) => (
        <span className="text-sm text-slate-600">
          {a.entity_type ? titleCase(a.entity_type) : "—"}
          {a.entity_id && <span className="ml-1 text-xs text-slate-400">#{a.entity_id.slice(0, 8)}</span>}
        </span>
      ),
    },
    { header: "IP", hideOn: "md", cell: (a) => <span className="font-mono text-xs text-slate-500">{a.ip_address || "—"}</span> },
    { header: "Time", cell: (a) => <span className="text-sm text-slate-500">{formatDate(a.created_at)}</span> },
    {
      header: "",
      className: "text-right w-1",
      cell: (a) =>
        a.old_data || a.new_data ? (
          <button className="btn-ghost px-2 py-1 text-xs" onClick={() => setDetail(a)}>
            Details
          </button>
        ) : null,
    },
  ];

  return (
    <div>
      <PageHeader title="Audit Logs" subtitle="Security and activity trail" />
      <Card className="p-4">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          {isSuperAdmin && (
            <TenantPicker tenants={scope.tenants} value={scope.selected} onChange={scope.setSelected} allowAll className="w-full sm:w-48" />
          )}
          <Select value={action} onChange={(e) => setAction(e.target.value)} className="w-full sm:w-56">
            {ACTIONS.map((a) => (
              <option key={a} value={a}>
                {a ? titleCase(a) : "All actions"}
              </option>
            ))}
          </Select>
          <span className="ml-auto text-sm text-slate-400">{list.meta?.total ?? 0} entries</span>
        </div>
        {list.error ? (
          <ErrorState message={list.error} onRetry={list.reload} />
        ) : (
          <>
            <DataTable
              columns={columns}
              rows={list.items}
              loading={list.loading}
              empty={<EmptyState icon={<Icon.Shield />} title="No audit entries" description="Actions across the platform will appear here." />}
            />
            <Pagination meta={list.meta} onPage={list.setPage} />
          </>
        )}
      </Card>

      <Modal open={!!detail} onClose={() => setDetail(null)} title="Audit entry" size="lg">
        {detail && (
          <div className="space-y-4 text-sm">
            <div className="grid grid-cols-2 gap-3">
              <Info label="Action" value={titleCase(detail.action)} />
              <Info label="Entity" value={detail.entity_type ? titleCase(detail.entity_type) : "—"} />
              <Info label="When" value={formatDate(detail.created_at)} />
              <Info label="IP" value={detail.ip_address || "—"} />
            </div>
            {detail.old_data && <JsonBlock title="Before" data={detail.old_data} />}
            {detail.new_data && <JsonBlock title="After" data={detail.new_data} />}
          </div>
        )}
      </Modal>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-slate-400">{label}</p>
      <p className="font-medium text-slate-700">{value}</p>
    </div>
  );
}

function JsonBlock({ title, data }: { title: string; data: Record<string, unknown> }) {
  return (
    <div>
      <p className="mb-1 text-xs font-semibold text-slate-500">{title}</p>
      <pre className="overflow-x-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}
