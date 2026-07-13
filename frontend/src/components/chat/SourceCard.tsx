import { useState } from "react";
import { Icon } from "@/components/ui/Icons";
import type { ChatSource } from "@/api/types";

export function SourceCards({ sources }: { sources: ChatSource[] }) {
  const [open, setOpen] = useState(false);
  if (!sources?.length) return null;
  return (
    <div className="mt-3">
      <button
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-700"
      >
        <Icon.Doc width={14} height={14} />
        {sources.length} source{sources.length > 1 ? "s" : ""}
        <Icon.ChevronDown width={14} height={14} className={`transition ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {sources.map((s) => (
            <div key={s.id} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <div className="flex items-start justify-between gap-2">
                <p className="min-w-0 flex-1 truncate text-sm font-medium text-slate-800">
                  {s.document_name || "Document"}
                </p>
                {/* Only 0..1 scores are percentages; older rows may hold a
                    reranker logit (e.g. 3.14) which would read as "314%". */}
                {typeof s.relevance_score === "number" && s.relevance_score > 0 && s.relevance_score <= 1 && (
                  <span className="flex-none rounded bg-brand-100 px-1.5 py-0.5 text-[10px] font-semibold text-brand-700">
                    {(s.relevance_score * 100).toFixed(0)}%
                  </span>
                )}
              </div>
              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-slate-400">
                {s.kb_name && <span>KB: {s.kb_name}</span>}
                {s.page_number != null && <span>Page {s.page_number}</span>}
              </div>
              {s.source_text_preview && (
                <p className="mt-1.5 line-clamp-2 text-xs text-slate-500">{s.source_text_preview}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
