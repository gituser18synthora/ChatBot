import { useMemo, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Icon } from "./Icons";
import type { PageMeta } from "@/api/types";

export interface Column<T> {
  header: string;
  cell: (row: T) => ReactNode;
  className?: string;
  hideOn?: "sm" | "md"; // hide below this breakpoint for responsiveness
  align?: "left" | "right" | "center";
}

const alignClass = (a?: "left" | "right" | "center") =>
  a === "right" ? "text-right" : a === "center" ? "text-center" : "text-left";

const hideClass = (h?: "sm" | "md") =>
  h === "sm" ? "hidden sm:table-cell" : h === "md" ? "hidden md:table-cell" : "";

export function DataTable<T extends { id: string }>({
  columns,
  rows,
  loading,
  empty,
  skeletonRows = 8,
}: {
  columns: Column<T>[];
  rows: T[];
  loading?: boolean;
  empty?: ReactNode;
  skeletonRows?: number;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-sm">
          <thead className="sticky top-0 z-10 bg-slate-50/95 backdrop-blur">
            <tr className="border-b border-slate-200 text-xs font-semibold uppercase tracking-wide text-slate-500">
              {columns.map((c, i) => (
                <th
                  key={i}
                  scope="col"
                  className={cn(
                    "whitespace-nowrap px-4 py-3",
                    alignClass(c.align),
                    hideClass(c.hideOn),
                    c.className
                  )}
                >
                  {c.header}
                </th>
              ))}
            </tr>
          </thead>

          <tbody className="divide-y divide-slate-100">
            {loading ? (
              Array.from({ length: skeletonRows }).map((_, r) => (
                <tr key={`skeleton-${r}`}>
                  {columns.map((c, i) => (
                    <td
                      key={i}
                      className={cn("px-4 py-3.5", hideClass(c.hideOn), c.className)}
                    >
                      <div
                        className="h-3.5 animate-pulse rounded bg-slate-200"
                        style={{ width: `${55 + ((i * 17 + r * 11) % 35)}%` }}
                      />
                    </td>
                  ))}
                </tr>
              ))
            ) : rows.length ? (
              rows.map((row) => (
                <tr key={row.id} className="transition-colors hover:bg-slate-50/70">
                  {columns.map((c, i) => (
                    <td
                      key={i}
                      className={cn(
                        "px-4 py-3.5 align-middle text-slate-700",
                        alignClass(c.align),
                        hideClass(c.hideOn),
                        c.className
                      )}
                    >
                      {c.cell(row)}
                    </td>
                  ))}
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={columns.length} className="px-4 py-12">
                  {empty ?? (
                    <div className="flex flex-col items-center justify-center gap-2 text-center text-slate-400">
                      <Icon.Search width={22} height={22} className="text-slate-300" />
                      <span className="text-sm font-medium text-slate-500">No records found</span>
                      <span className="text-xs text-slate-400">Try adjusting your filters or search.</span>
                    </div>
                  )}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function Pagination({ meta, onPage }: { meta?: PageMeta; onPage: (p: number) => void }) {
  if (!meta || meta.pages <= 1) return null;
  const { page, pages, total, per_page } = meta;
  const from = (page - 1) * per_page + 1;
  const to = Math.min(page * per_page, total);

  // Build a compact page-number list: first, last, current ±1, with ellipses.
  const pageItems = useMemo(() => {
    const items: (number | "ellipsis")[] = [];
    const add = (p: number) => items.push(p);
    const windowStart = Math.max(2, page - 1);
    const windowEnd = Math.min(pages - 1, page + 1);

    add(1);
    if (windowStart > 2) items.push("ellipsis");
    for (let p = windowStart; p <= windowEnd; p++) add(p);
    if (windowEnd < pages - 1) items.push("ellipsis");
    if (pages > 1) add(pages);

    return items;
  }, [page, pages]);

  return (
    <div className="flex flex-col items-center justify-between gap-3 px-1 py-3 text-sm text-slate-500 sm:flex-row">
      <span>
        Showing <span className="font-medium text-slate-700">{from}</span>–
        <span className="font-medium text-slate-700">{to}</span> of{" "}
        <span className="font-medium text-slate-700">{total}</span>
      </span>

      <div className="flex items-center gap-1">
        <button
          type="button"
          className="btn-secondary px-2.5 py-1.5 disabled:opacity-40"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
          aria-label="Previous page"
        >
          <Icon.ChevronDown className="rotate-90" width={16} height={16} />
        </button>

        <div className="hidden items-center gap-1 sm:flex">
          {pageItems.map((item, i) =>
            item === "ellipsis" ? (
              <span key={`e-${i}`} className="px-1.5 text-slate-400">
                …
              </span>
            ) : (
              <button
                key={item}
                type="button"
                onClick={() => onPage(item)}
                aria-current={item === page ? "page" : undefined}
                className={cn(
                  "min-w-[28px] rounded-md px-2 py-1.5 text-sm font-medium transition-colors",
                  item === page
                    ? "bg-primary text-white"
                    : "text-slate-600 hover:bg-slate-100"
                )}
              >
                {item}
              </button>
            )
          )}
        </div>

        <span className="px-2 text-slate-600 sm:hidden">
          Page {page} / {pages}
        </span>

        <button
          type="button"
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