import { describe, expect, it } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { useList } from "./useList";
import type { Paginated } from "@/api/types";

const meta = { page: 1, per_page: 20, total: 1, pages: 1 };
const page = (items: string[]): Paginated<string> => ({ items, meta });

describe("useList silent reload (status polling)", () => {
  it("keeps rows on screen and loading=false during a silent reload", async () => {
    let resolve: (v: Paginated<string>) => void;
    let calls = 0;
    const { result } = renderHook(() =>
      useList<string>(() => {
        calls++;
        if (calls === 1) return Promise.resolve(page(["processing-doc"]));
        return new Promise<Paginated<string>>((r) => (resolve = r));
      }),
    );
    await waitFor(() => expect(result.current.items).toEqual(["processing-doc"]));

    act(() => result.current.reload({ silent: true }));
    // While the poll request is in flight: no spinner, rows untouched.
    await waitFor(() => expect(calls).toBe(2));
    expect(result.current.loading).toBe(false);
    expect(result.current.items).toEqual(["processing-doc"]);

    act(() => resolve!(page(["indexed-doc"])));
    await waitFor(() => expect(result.current.items).toEqual(["indexed-doc"]));
    expect(result.current.loading).toBe(false);
  });

  it("a failed silent poll keeps existing data instead of clearing it", async () => {
    let calls = 0;
    const { result } = renderHook(() =>
      useList<string>(() => {
        calls++;
        return calls === 1 ? Promise.resolve(page(["doc"])) : Promise.reject(new Error("boom"));
      }),
    );
    await waitFor(() => expect(result.current.items).toEqual(["doc"]));

    act(() => result.current.reload({ silent: true }));
    await waitFor(() => expect(calls).toBe(2));
    await waitFor(() => expect(result.current.items).toEqual(["doc"]));
    expect(result.current.error).toBeNull();
  });

  it("a normal reload still shows the loading state", async () => {
    let resolve: (v: Paginated<string>) => void;
    let calls = 0;
    const { result } = renderHook(() =>
      useList<string>(() => {
        calls++;
        if (calls === 1) return Promise.resolve(page(["v1"]));
        return new Promise<Paginated<string>>((r) => (resolve = r));
      }),
    );
    await waitFor(() => expect(result.current.items).toEqual(["v1"]));

    act(() => result.current.reload());
    await waitFor(() => expect(result.current.loading).toBe(true));

    act(() => resolve!(page(["v2"])));
    await waitFor(() => expect(result.current.items).toEqual(["v2"]));
    expect(result.current.loading).toBe(false);
  });
});
