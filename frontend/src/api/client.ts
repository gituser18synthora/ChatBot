import axios, { AxiosError, AxiosInstance } from "axios";
import type { ApiEnvelope, PageMeta, Paginated } from "./types";

const ACCESS_KEY = "cb_access_token";
const REFRESH_KEY = "cb_refresh_token";

export const tokenStore = {
  get access() {
    return localStorage.getItem(ACCESS_KEY);
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY);
  },
  set(access: string, refresh?: string) {
    localStorage.setItem(ACCESS_KEY, access);
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

/** A normalized, frontend-safe error. `message` is always safe to display. */
export class ApiRequestError extends Error {
  code: string;
  status: number;
  constructor(message: string, code: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

const baseURL = import.meta.env.VITE_API_BASE_URL || "";

export const http: AxiosInstance = axios.create({
  baseURL,
  headers: { "Content-Type": "application/json" },
});

http.interceptors.request.use((config) => {
  const token = tokenStore.access;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  // For file uploads, strip the JSON default so the browser sets
  // `multipart/form-data; boundary=…` itself (a boundary-less header is unparsable).
  if (typeof FormData !== "undefined" && config.data instanceof FormData) {
    config.headers.delete?.("Content-Type");
  }
  return config;
});

// Single-flight refresh so concurrent 401s don't stampede the refresh endpoint.
let refreshing: Promise<string | null> | null = null;

async function tryRefresh(): Promise<string | null> {
  const refresh = tokenStore.refresh;
  if (!refresh) return null;
  try {
    const resp = await axios.post<ApiEnvelope<{ access_token: string }>>(
      `${baseURL}/api/v1/auth/refresh`,
      {},
      { headers: { Authorization: `Bearer ${refresh}` } },
    );
    const token = resp.data.data.access_token;
    tokenStore.set(token);
    return token;
  } catch {
    return null;
  }
}

http.interceptors.response.use(
  (r) => r,
  async (error: AxiosError<ApiEnvelope<unknown>>) => {
    const original = error.config as (typeof error.config & { _retried?: boolean }) | undefined;
    const status = error.response?.status ?? 0;
    const isAuthCall = original?.url?.includes("/auth/login") || original?.url?.includes("/auth/refresh");

    if (status === 401 && original && !original._retried && !isAuthCall) {
      original._retried = true;
      refreshing = refreshing || tryRefresh();
      const newToken = await refreshing;
      refreshing = null;
      if (newToken) {
        original.headers = original.headers ?? {};
        original.headers.Authorization = `Bearer ${newToken}`;
        return http(original);
      }
      // Refresh failed — force logout.
      tokenStore.clear();
      if (!location.pathname.startsWith("/login")) {
        location.assign("/login?expired=1");
      }
    }

    const payload = error.response?.data;
    let message = payload?.error?.message;
    if (!message) {
      if (status === 413) {
        // Body exceeded the server's limit — describe the real problem, not a
        // generic "something went wrong" or network error.
        message = "The file size exceeds the maximum allowed limit.";
      } else if (status === 0) {
        message = "Unable to reach the server. Check your connection and try again.";
      } else {
        message = "Something went wrong. Please try again.";
      }
    }
    const code = payload?.error?.code || (status === 413 ? "file_too_large" : "error");
    throw new ApiRequestError(message, code, status);
  },
);

// ── Helpers that unwrap the { success, data, meta } envelope ──
export async function getData<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const resp = await http.get<ApiEnvelope<T>>(url, { params });
  return resp.data.data;
}

export async function getPaginated<T>(
  url: string,
  params?: Record<string, unknown>,
): Promise<Paginated<T>> {
  const resp = await http.get<ApiEnvelope<T[]>>(url, { params });
  return { items: resp.data.data, meta: resp.data.meta as PageMeta };
}

export async function postData<T>(url: string, body?: unknown): Promise<T> {
  const resp = await http.post<ApiEnvelope<T>>(url, body);
  return resp.data.data;
}

export async function putData<T>(url: string, body?: unknown): Promise<T> {
  const resp = await http.put<ApiEnvelope<T>>(url, body);
  return resp.data.data;
}

export async function patchData<T>(url: string, body?: unknown): Promise<T> {
  const resp = await http.patch<ApiEnvelope<T>>(url, body);
  return resp.data.data;
}

export async function deleteData<T>(url: string): Promise<T> {
  const resp = await http.delete<ApiEnvelope<T>>(url);
  return resp.data.data;
}
