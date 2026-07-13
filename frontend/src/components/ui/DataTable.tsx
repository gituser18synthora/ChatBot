import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { LoadingBlock } from "./primitives";
import { Icon } from "./Icons";
import type { PageMeta } from "@/api/types";

export interface Column<T> {
  header: string;
  cell: (row: T) => ReactNode;
  className?: string;
  hideOn?: "sm" | "md"; // hide below this breakpoint for responsiveness
}

export function DataTable<T extends { id: string }>({
  columns,
  rows,
  loading,
  empty,
}: {
  columns: Column<T>[];
  rows: T[];
  loading?: boolean;
  empty?: ReactNode;
}) {
  const hideClass = (h?: "sm" | "md") =>
    h === "sm" ? "hidden sm:table-cell" : h === "md" ? "hidden md:table-cell" : "";

  if (loading) return <LoadingBlock />;
  if (!rows.length) return <>{empty}</>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
            {columns.map((c, i) => (
              <th key={i} className={cn("px-4 py-3", hideClass(c.hideOn), c.className)}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-b border-slate-100 transition hover:bg-slate-50/70">
              {columns.map((c, i) => (
                <td key={i} className={cn("px-4 py-3 align-middle text-slate-700", hideClass(c.hideOn), c.className)}>
                  {c.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Pagination({ meta, onPage }: { meta?: PageMeta; onPage: (p: number) => void }) {
  if (!meta || meta.pages <= 1) return null;
  const { page, pages, total, per_page } = meta;
  const from = (page - 1) * per_page + 1;
  const to = Math.min(page * per_page, total);
  return (
    <div className="flex flex-col items-center justify-between gap-3 px-1 py-3 text-sm text-slate-500 sm:flex-row">
      <span>
        Showing <span className="font-medium text-slate-700">{from}</span>–
        <span className="font-medium text-slate-700">{to}</span> of{" "}
        <span className="font-medium text-slate-700">{total}</span>
      </span>
      <div className="flex items-center gap-1">
        <button
          className="btn-secondary px-2.5 py-1.5 disabled:opacity-40"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
          aria-label="Previous page"
        >
          <Icon.ChevronDown className="rotate-90" width={16} height={16} />
        </button>
        <span className="px-2 text-slate-600">
          Page {page} / {pages}
        </span>
        <button
          className="btn-secondary px-2.5 py-1.5 disabled:opacity-40"
          disabled={page >= pages}
          onClick={() => onPage(page + 1)}
          aria-label="Next page"
        >
          <Icon.ChevronDown className="-rotate-90" width={16} height={16} />
        </button>
      </div>
    </div>
  );
}
