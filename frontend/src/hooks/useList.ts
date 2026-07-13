import { useCallback, useEffect, useRef, useState } from "react";
import type { PageMeta, Paginated } from "@/api/types";
import { ApiRequestError } from "@/api/client";

interface ListState<T> {
  items: T[];
  meta?: PageMeta;
  loading: boolean;
  error: string | null;
  page: number;
  search: string;
  setPage: (p: number) => void;
  setSearch: (s: string) => void;
  /** Refetch. `silent` refreshes in the background: no loading state, and the
   * current items stay on screen until the new data arrives (for polling). */
  reload: (opts?: { silent?: boolean }) => void;
}

/**
 * Standard list controller: pagination + debounced search + loading/error.
 * `fetcher` receives (page, search) and returns a Paginated result.
 */
export function useList<T>(
  fetcher: (page: number, search: string) => Promise<Paginated<T>>,
  deps: unknown[] = [],
): ListState<T> {
  const [items, setItems] = useState<T[]>([]);
  const [meta, setMeta] = useState<PageMeta>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [search, setSearchRaw] = useState("");
  const [nonce, setNonce] = useState(0);
  const debounce = useRef<number>();
  const silentRef = useRef(false);

  const setSearch = useCallback((s: string) => {
    setSearchRaw(s);
    setPage(1);
  }, []);

  const reload = useCallback((opts?: { silent?: boolean }) => {
    silentRef.current = !!opts?.silent;
    setNonce((n) => n + 1);
  }, []);

  useEffect(() => {
    let active = true;
    // A silent reload (status polling) must not blank the table: keep the
    // current rows and loading=false, and swap the data in when it arrives.
    const silent = silentRef.current;
    silentRef.current = false;
    window.clearTimeout(debounce.current);
    debounce.current = window.setTimeout(
      async () => {
        if (!silent) {
          setLoading(true);
          setError(null);
        }
        try {
          const res = await fetcher(page, search);
          if (!active) return;
          setItems(res.items);
          setMeta(res.meta);
          if (silent) setError(null);
        } catch (e) {
          if (!active || silent) return; // a failed background poll keeps existing data
          setError(e instanceof ApiRequestError ? e.message : "Failed to load data.");
          setItems([]);
        } finally {
          if (active && !silent) setLoading(false);
        }
      },
      search ? 300 : 0,
    );
    return () => {
      active = false;
      window.clearTimeout(debounce.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, search, nonce, ...deps]);

  return { items, meta, loading, error, page, search, setPage, setSearch, reload };
}
