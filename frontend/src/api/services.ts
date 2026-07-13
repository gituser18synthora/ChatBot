// Typed API service layer. One place per resource; components never build URLs.
import {
  deleteData,
  getData,
  getPaginated,
  http,
  patchData,
  postData,
  putData,
  tokenStore,
} from "./client";
import type {
  AdminVoiceSettings,
  AuditLog,
  ChatMessage,
  ChatSession,
  CostBreakdown,
  DashboardStats,
  DocumentItem,
  KnowledgeBase,
  Paginated,
  Profile,
  Role,
  SelectableKb,
  Tenant,
  TenantCreateInput,
  TokenBreakdown,
  User,
  UserKbAccess,
  EffectiveVoiceSettings,
  VoiceSettings,
} from "./types";

const V1 = "/api/v1";

export interface ListParams {
  page?: number;
  per_page?: number;
  search?: string;
  status?: string;
  role?: string;
  tenant_id?: string;
  [key: string]: unknown;
}

// ── Auth ──────────────────────────────────────────────────────
export const authApi = {
  async login(email: string, password: string) {
    const data = await postData<{ access_token: string; refresh_token: string; user: User }>(
      `${V1}/auth/login`,
      { email, password },
    );
    tokenStore.set(data.access_token, data.refresh_token);
    return data.user;
  },
  async me() {
    return (await getData<{ user: User }>(`${V1}/auth/me`)).user;
  },
  async logout() {
    try {
      await postData(`${V1}/auth/logout`);
    } finally {
      tokenStore.clear();
    }
  },
};

// ── Tenants ───────────────────────────────────────────────────
export interface TenantCreated extends Tenant {
  admin: { id: string; name: string; email: string } | null;
}
export const tenantApi = {
  list: (p: ListParams) => getPaginated<Tenant>(`${V1}/admin/tenants`, p),
  get: (id: string) => getData<Tenant>(`${V1}/admin/tenants/${id}`),
  create: (body: TenantCreateInput) => postData<TenantCreated>(`${V1}/admin/tenants`, body),
  update: (id: string, body: Partial<Tenant>) => putData<Tenant>(`${V1}/admin/tenants/${id}`, body),
  remove: (id: string) => deleteData(`${V1}/admin/tenants/${id}`),
};

// ── Profile (self-service) ────────────────────────────────────
export const profileApi = {
  get: () => getData<Profile>(`${V1}/profile`),
  updateTenant: (body: Partial<Pick<Tenant, "tenant_name" | "contact_name" | "contact_email" | "rag_mode">>) =>
    putData<Tenant>(`${V1}/profile/tenant`, body),
  changePassword: (current_password: string, new_password: string) =>
    putData<{ message: string }>(`${V1}/profile/password`, { current_password, new_password }),
};

// ── Users ─────────────────────────────────────────────────────
export const userApi = {
  list: (p: ListParams) => getPaginated<User>(`${V1}/users`, p),
  get: (id: string) => getData<User>(`${V1}/users/${id}`),
  create: (body: {
    name: string;
    email: string;
    password: string;
    role: Role;
    tenant_id?: string | null;
    is_active?: boolean;
    // Initial KB scoping: Chat Users empty/omitted => no KB access;
    // Tenant Admins empty/omitted => all tenant KBs.
    kb_ids?: string[];
  }) => postData<User>(`${V1}/users`, body),
  update: (id: string, body: Partial<{ name: string; password: string; role: Role }>) =>
    putData<User>(`${V1}/users/${id}`, body),
  setStatus: (id: string, is_active: boolean) =>
    patchData<User>(`${V1}/users/${id}/status`, { is_active }),
  remove: (id: string) => deleteData(`${V1}/users/${id}`),
  // Per-user Knowledge Base scoping.
  getKbs: (id: string) => getData<UserKbAccess>(`${V1}/users/${id}/knowledge-bases`),
  setKbs: (id: string, kb_ids: string[]) =>
    putData<UserKbAccess>(`${V1}/users/${id}/knowledge-bases`, { kb_ids }),
};

// ── Knowledge Bases ───────────────────────────────────────────
export const kbApi = {
  list: (tenantId: string, p: ListParams) =>
    getPaginated<KnowledgeBase>(`${V1}/tenants/${tenantId}/knowledge-bases`, p),
  selectable: (tenantId: string) =>
    getData<SelectableKb[]>(`${V1}/tenants/${tenantId}/knowledge-bases/selectable`),
  get: (id: string) => getData<KnowledgeBase>(`${V1}/knowledge-bases/${id}`),
  create: (tenantId: string, body: Partial<KnowledgeBase>) =>
    postData<KnowledgeBase>(`${V1}/tenants/${tenantId}/knowledge-bases`, body),
  update: (id: string, body: Partial<KnowledgeBase>) =>
    putData<KnowledgeBase>(`${V1}/knowledge-bases/${id}`, body),
  remove: (id: string) => deleteData(`${V1}/knowledge-bases/${id}`),
};

// ── Documents ─────────────────────────────────────────────────
export const documentApi = {
  list: (kbId: string, p: ListParams) =>
    getPaginated<DocumentItem>(`${V1}/knowledge-bases/${kbId}/documents`, p),
  get: (id: string) => getData<DocumentItem>(`${V1}/documents/${id}`),
  remove: (id: string) => deleteData<{ message: string; note?: string }>(`${V1}/documents/${id}`),
  async upload(
    kbId: string,
    file: File,
    onProgress?: (pct: number) => void,
  ): Promise<DocumentItem> {
    const form = new FormData();
    form.append("file", file);
    // Do NOT set Content-Type here — the browser must set
    // `multipart/form-data; boundary=…` itself, or the server can't parse it.
    const resp = await http.post(`${V1}/knowledge-bases/${kbId}/documents/upload`, form, {
      onUploadProgress: (e) => {
        if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100));
      },
    });
    return resp.data.data as DocumentItem;
  },
  async createKbAndUpload(
    tenantId: string,
    file: File,
    kbName?: string,
    onProgress?: (pct: number) => void,
  ): Promise<{ knowledge_base: KnowledgeBase; document: DocumentItem }> {
    const form = new FormData();
    form.append("file", file);
    if (kbName) form.append("kb_name", kbName);
    const resp = await http.post(`${V1}/tenants/${tenantId}/knowledge-bases/documents/upload`, form, {
      onUploadProgress: (e) => {
        if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100));
      },
    });
    return resp.data.data as { knowledge_base: KnowledgeBase; document: DocumentItem };
  },
  async retry(id: string, file: File): Promise<DocumentItem> {
    const form = new FormData();
    form.append("file", file);
    const resp = await http.post(`${V1}/documents/${id}/retry`, form);
    return resp.data.data as DocumentItem;
  },
};

// ── Chat ──────────────────────────────────────────────────────
export const chatApi = {
  // The KBs the signed-in user may ground a chat in (assignment-scoped).
  knowledgeBases: () => getData<SelectableKb[]>(`${V1}/chat/knowledge-bases`),
  listSessions: (p: ListParams) => getPaginated<ChatSession>(`${V1}/chat/sessions`, p),
  getSession: (id: string) => getData<ChatSession>(`${V1}/chat/sessions/${id}`),
  createSession: (title: string | null, kb_ids: string[]) =>
    postData<ChatSession>(`${V1}/chat/sessions`, { title, kb_ids }),
  rename: (id: string, title: string) => putData<ChatSession>(`${V1}/chat/sessions/${id}`, { title }),
  remove: (id: string) => deleteData(`${V1}/chat/sessions/${id}`),
  send: (id: string, message: string) =>
    postData<{ assistant_message: ChatMessage; session_id: string; session_title: string | null }>(
      `${V1}/chat/sessions/${id}/messages`,
      { message },
    ),
};

// ── Super Tenant: KB sharing / assignment ─────────────────────
export interface KbAssignment {
  assignment_id?: string;
  tenant_id: string;
  tenant_name: string | null;
  created_at?: string;
}
export interface ShareableKb extends KnowledgeBase {
  assigned_tenants: KbAssignment[];
}
export const superTenantApi = {
  info: () => getData<{ super_tenant: Tenant | null }>(`${V1}/super-tenant`),
  shareableKbs: (p: ListParams) => getPaginated<ShareableKb>(`${V1}/super-tenant/knowledge-bases`, p),
  assign: (kbId: string, tenantId: string) =>
    postData(`${V1}/super-tenant/knowledge-bases/${kbId}/assignments`, { tenant_id: tenantId }),
  unassign: (kbId: string, tenantId: string) =>
    deleteData(`${V1}/super-tenant/knowledge-bases/${kbId}/assignments/${tenantId}`),
};

// ── Conversations (admin, tenant-wide) ────────────────────────
export interface AdminConversation extends ChatSession {
  user_name?: string | null;
  message_count?: number;
}
export const conversationApi = {
  list: (p: ListParams) => getPaginated<AdminConversation>(`${V1}/admin/conversations`, p),
  get: (id: string) => getData<ChatSession>(`${V1}/admin/conversations/${id}`),
};

// ── Analytics ─────────────────────────────────────────────────
export const analyticsApi = {
  dashboard: (tenantId?: string) =>
    getData<DashboardStats>(`${V1}/analytics/dashboard`, tenantId ? { tenant_id: tenantId } : undefined),
  costs: (tenantId?: string, days = 30) =>
    getData<CostBreakdown>(`${V1}/analytics/costs`, { tenant_id: tenantId, days }),
  tokens: (tenantId?: string, days = 30) =>
    getData<TokenBreakdown>(`${V1}/analytics/tokens`, { tenant_id: tenantId, days }),
  kb: (kbId: string) =>
    getData<{ kb_id: string; document_count: number; processing: number; failed: number; citations: number }>(
      `${V1}/analytics/knowledge-base/${kbId}`,
    ),
};

// ── Voice settings (TTS) ──────────────────────────────────────
export const voiceApi = {
  getPlatform: () => getData<AdminVoiceSettings>(`${V1}/admin/voice-settings`),
  updatePlatform: (body: Partial<AdminVoiceSettings>) =>
    putData<AdminVoiceSettings>(`${V1}/admin/voice-settings`, body),
  getTenant: () => getData<AdminVoiceSettings>(`${V1}/admin/voice-settings/tenant`),
  updateTenant: (body: Partial<VoiceSettings>) =>
    putData<AdminVoiceSettings>(`${V1}/admin/voice-settings/tenant`, body),
  resetTenant: () => deleteData<AdminVoiceSettings>(`${V1}/admin/voice-settings/tenant`),
  getEffective: () => getData<EffectiveVoiceSettings>(`${V1}/voice-settings/effective`),
};

// ── Audit ─────────────────────────────────────────────────────
export const auditApi = {
  list: (p: ListParams & { action?: string; entity_type?: string }) =>
    getPaginated<AuditLog>(`${V1}/audit-logs`, p),
};

export type { Paginated };
