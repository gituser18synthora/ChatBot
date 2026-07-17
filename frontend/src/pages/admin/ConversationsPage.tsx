import { useState } from "react";
import { conversationApi, type AdminConversation } from "@/api/services";
import { useList } from "@/hooks/useList";
import { useAsync } from "@/hooks/useAsync";
import { useAuth } from "@/context/AuthContext";
import { useTenantScope, TenantPicker } from "@/components/common/TenantPicker";
import { PageHeader, SearchInput, EmptyState, ErrorState, Card, Badge, LoadingBlock } from "@/components/ui/primitives";
import { DataTable, Pagination, type Column } from "@/components/ui/DataTable";
import { Modal } from "@/components/ui/Modal";
import { MessageBubble } from "@/components/chat/MessageBubble";
import { Icon } from "@/components/ui/Icons";
import { formatDate, relativeTime } from "@/lib/utils";
import type { ChatSession } from "@/api/types";

export function ConversationsPage() {
  const { isSuperAdmin } = useAuth();
  const scope = useTenantScope(true);
  const list = useList<AdminConversation>(
    (page, search) =>
      conversationApi.list({ page, search, tenant_id: isSuperAdmin ? scope.selected || undefined : undefined }),
    [scope.selected],
  );
  const [openId, setOpenId] = useState<string | null>(null);

  const columns: Column<AdminConversation>[] = [
    {
      header: "Conversation",
      cell: (c) => (
        <div>
          <p className="font-medium text-slate-900">{c.title || "Untitled chat"}</p>
          <p className="text-xs text-slate-400">{c.message_count ?? 0} messages</p>
        </div>
      ),
    },
    { header: "User", hideOn: "sm", cell: (c) => <span className="text-sm text-slate-600">{c.user_name || "—"}</span> },
    {
      header: "Knowledge Bases",
      hideOn: "md",
      cell: (c) =>
        c.kb_ids?.length ? <Badge tone="blue">{c.kb_ids.length} KB</Badge> : <span className="text-xs text-slate-400">General</span>,
    },
    { header: "Updated", hideOn: "sm", cell: (c) => <span className="text-sm text-slate-500">{relativeTime(c.updated_at)}</span> },
    {
      header: "",
      className: "text-right w-1",
      cell: (c) => (
        <button className="btn-secondary px-2.5 py-1.5 text-xs" onClick={() => setOpenId(c.id)}>
          View
        </button>
      ),
    },
  ];

  return (
    <div>
      <PageHeader title="Conversations" subtitle="Chat activity across your tenant" />
      <Card className="p-4">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <SearchInput value={list.search} onChange={list.setSearch} placeholder="Search conversations…" />
          {isSuperAdmin && (
            <TenantPicker tenants={scope.tenants} value={scope.selected} onChange={scope.setSelected} allowAll className="w-full sm:w-48" />
          )}
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
              empty={<EmptyState icon={<Icon.Chat />} title="No conversations yet" description="Chats will appear here once users start messaging." />}
            />
            <Pagination meta={list.meta} onPage={list.setPage} />
          </>
        )}
      </Card>

      {openId && <ConversationModal id={openId} onClose={() => setOpenId(null)} />}
    </div>
  );
}

function ConversationModal({ id, onClose }: { id: string; onClose: () => void }) {
  const { data, loading, error, reload } = useAsync<ChatSession>(() => conversationApi.get(id), [id]);
  return (
    <Modal open onClose={onClose} title={data?.title || "Conversation"} size="lg">
      {loading ? (
        <LoadingBlock />
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : (
        <div>
          <p className="mb-4 text-xs text-slate-400">Started {formatDate(data?.created_at)}</p>
          <div className="space-y-4">
            {(data?.messages || []).map((m) => (
              <MessageBubble key={m.id} message={m} readOnly />
            ))}
            {!data?.messages?.length && <p className="text-sm text-slate-400">No messages in this conversation.</p>}
          </div>
        </div>
      )}
    </Modal>
  );
}
