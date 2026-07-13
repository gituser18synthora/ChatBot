import { useEffect, useState } from "react";
import { chatApi } from "@/api/services";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { Modal } from "@/components/ui/Modal";
import { Spinner, Badge, ErrorState } from "@/components/ui/primitives";
import { Icon } from "@/components/ui/Icons";
import { cn } from "@/lib/utils";
import type { ChatSession, SelectableKb } from "@/api/types";

/**
 * Admin-only dialog for optionally pinning a new chat to specific KBs.
 * Chat Users never see this — their New Chat creates a session immediately
 * (ChatPage.startNewChat) with their Knowledge Bases applied automatically.
 */
export function NewChatModal({ onClose, onCreated }: { onClose: () => void; onCreated: (s: ChatSession) => void }) {
  const { user } = useAuth();
  const toast = useToast();
  const [kbs, setKbs] = useState<SelectableKb[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [loadingKbs, setLoadingKbs] = useState(true);
  const [kbError, setKbError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const loadKbs = () => {
    setLoadingKbs(true);
    setKbError(null);
    chatApi
      .knowledgeBases()
      .then(setKbs)
      .catch((e: any) => setKbError(e.message || "Could not load knowledge bases."))
      .finally(() => setLoadingKbs(false));
  };

  useEffect(() => {
    if (!user?.tenant_id) {
      setLoadingKbs(false);
      return;
    }
    loadKbs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.tenant_id]);

  const toggle = (id: string) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const create = async () => {
    setCreating(true);
    try {
      // No manual title: it is generated automatically from the first message.
      const session = await chatApi.createSession(null, selected);
      onCreated(session);
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setCreating(false);
    }
  };

  const kbStatus = (kb: SelectableKb) => {
    if (kb.document_count === undefined) return null;
    if (kb.document_count === 0) return { label: "No documents", tone: "gray" as const };
    if (!kb.ready) return { label: "Indexing…", tone: "amber" as const };
    return null;
  };

  return (
    <Modal
      open
      onClose={onClose}
      title="Start a new chat"
      footer={
        <>
          <button className="btn-secondary" onClick={onClose} disabled={creating}>
            Cancel
          </button>
          <button className="btn-primary" onClick={create} disabled={creating}>
            {creating && <Spinner className="text-white" />}
            Start chat
          </button>
        </>
      }
    >
      <div>
        <p className="label">Knowledge bases</p>
        <p className="mb-2 text-xs text-slate-400">
          Optionally narrow this chat to specific knowledge bases. Leave empty to use all the
          knowledge bases available to you — the assistant grounds document questions in them
          automatically.
        </p>
        {loadingKbs ? (
          <div className="flex items-center gap-2 py-4 text-sm text-slate-400">
            <Spinner /> Loading knowledge bases…
          </div>
        ) : kbError ? (
          <ErrorState message={kbError} onRetry={loadKbs} />
        ) : kbs.length === 0 ? (
          <p className="rounded-lg bg-slate-50 px-3 py-3 text-sm text-slate-500">
            No ready Knowledge Bases are available for chat yet. Upload documents and wait for
            indexing to finish.
          </p>
        ) : (
          <div className="grid max-h-56 grid-cols-1 gap-2 overflow-y-auto sm:grid-cols-2">
            {kbs.map((kb) => {
              const on = selected.includes(kb.id);
              const status = kbStatus(kb);
              return (
                <button
                  key={kb.id}
                  type="button"
                  onClick={() => toggle(kb.id)}
                  disabled={kb.ready === false}
                  className={cn(
                    "flex items-center gap-2.5 rounded-lg border px-3 py-2.5 text-left text-sm transition",
                    kb.ready === false
                      ? "cursor-not-allowed border-slate-200 bg-slate-50 text-slate-400"
                      : on
                      ? "border-brand-500 bg-brand-50 text-brand-800"
                      : "border-slate-200 hover:border-slate-300",
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
                  {status && (
                    <span
                      className={cn(
                        "flex-none rounded px-1.5 py-0.5 text-[10px] font-semibold",
                        status.tone === "amber" ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-500",
                      )}
                    >
                      {status.label}
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
        )}
        {selected.length > 0 && (
          <div className="mt-2">
            <Badge tone="blue">{selected.length} knowledge base{selected.length > 1 ? "s" : ""} selected</Badge>
          </div>
        )}
      </div>
    </Modal>
  );
}
