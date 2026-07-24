// Shared API types mirroring the backend response envelope and models.

export type Role = "super_admin" | "tenant_admin" | "chat_user";

export interface ApiEnvelope<T> {
  success: boolean;
  data: T;
  meta?: PageMeta;
  error?: { code: string; message: string };
}

export interface PageMeta {
  page: number;
  per_page: number;
  total: number;
  pages: number;
}

export interface Paginated<T> {
  items: T[];
  meta: PageMeta;
}

export interface User {
  id: string;
  tenant_id: string | null;
  name: string;
  email: string;
  role: Role;
  is_active: boolean;
  last_login_at: string | null;
  created_at?: string;
  token?: string | null;
}

// Tenant answering policy: rag_first allows general AI for clearly general
// questions; rag_only answers exclusively from Knowledge Bases.
export type RagMode = "rag_only" | "rag_first";

export interface Tenant {
  id: string;
  tenant_name: string;
  tenant_code: string;
  status: "active" | "inactive";
  is_super_tenant?: boolean;
  rag_mode?: RagMode;
  contact_name: string | null;
  contact_email: string | null;
  created_at: string;
  updated_at: string;
}

export type KnowledgeBaseStatus = "pending" | "processing" | "ready" | "failed" | "inactive";

// Note: tenants are always created as normal tenants — the backend rejects
// is_super_tenant on create; designate the Super Tenant afterwards via update.
export interface TenantCreateInput {
  tenant_name: string;
  status?: "active" | "inactive";
  contact_name?: string | null;
  contact_email?: string | null;
  // Tenant login (created together with the tenant).
  admin_name?: string;
  admin_email?: string;
  admin_password?: string;
}

// A KB entry for admin scoping or for the signed-in user's effective chat scope.
export interface SelectableKb {
  id: string;
  kb_name: string;
  shared?: boolean;
  assigned?: boolean;
  status?: KnowledgeBaseStatus;
  status_message?: string | null;
  // Present on /chat/knowledge-bases: ingestion visibility for the chat UI.
  document_count?: number;
  indexed_count?: number;
  ready?: boolean;
}

export interface UserKbAccess {
  user_id: string;
  assigned_kb_ids: string[];
  uses_all_kbs: boolean;
  available: SelectableKb[];
}

export interface Profile {
  user: User;
  tenant: Tenant | null;
}

export interface KnowledgeBase {
  id: string;
  tenant_id: string;
  kb_name: string;
  description: string | null;
  status: KnowledgeBaseStatus;
  status_message: string | null;
  ready?: boolean;
  created_by: string | null;
  document_count?: number;
  indexed_count?: number;
  processing_count?: number;
  failed_count?: number;
  created_at: string;
  updated_at: string;
}

export type DocumentStatus =
  | "pending"
  | "uploading"
  | "processing"
  | "completed"
  | "failed"
  | "deleted";

export interface DocumentItem {
  id: string;
  tenant_id: string;
  kb_id: string;
  original_filename: string;
  content_type: string | null;
  file_size_bytes: number;
  upload_status: DocumentStatus;
  ingestion_error: string | null;
  uploaded_by: string | null;
  uploaded_at: string | null;
  processed_at: string | null;
  created_at: string;
}

export type AnswerMode =
  | "normal"
  | "document_rag"
  | "mixed"
  | "no_document_evidence"
  | "error";

export interface ChatSource {
  id: string;
  kb_id: string | null;
  kb_name: string | null;
  document_id: string | null;
  document_name: string | null;
  page_number: number | null;
  chunk_id: string | null;
  relevance_score: number | null;
  source_text_preview: string | null;
}

export interface ChatMessage {
  id: string;
  chat_session_id: string;
  role: "user" | "assistant" | "system";
  message_text: string;
  answer_mode: AnswerMode | null;
  model_name: string | null;
  total_tokens: number;
  estimated_cost_usd: number;
  latency_ms: number | null;
  created_at: string;
  sources?: ChatSource[];
}

export interface ChatSession {
  id: string;
  tenant_id: string;
  user_id: string;
  title: string | null;
  status: string;
  kb_ids: string[];
  kb_names?: (string | null)[];
  messages?: ChatMessage[];
  created_at: string;
  updated_at: string;
}

export interface DashboardStats {
  total_tenants: number;
  active_tenants: number;
  total_knowledge_bases: number;
  total_documents: number;
  documents_processing: number;
  failed_documents: number;
  total_users: number;
  total_conversations: number;
  today_token_usage: number;
  today_openai_cost: number;
  monthly_openai_cost: number;
}

export interface CostBreakdown {
  daily: { day: string; cost_usd: number; tokens: number }[];
  by_model: { model: string; cost_usd: number; tokens: number }[];
  by_tenant?: { tenant_id: string; tenant_name: string | null; cost_usd: number }[];
  rag_queries: number;
  general_queries: number;
}

export interface TokenBreakdown {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  document_tokens: number;
}

export interface AuditLog {
  id: string;
  tenant_id: string | null;
  user_id: string | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  old_data: Record<string, unknown> | null;
  new_data: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

export type VoiceGender = "male" | "female" | "neutral";

export interface VoiceSettings {
  enabled: boolean;
  provider: string;
  voice_name: string | null;
  language: string | null;
  gender: VoiceGender | null;
  rate: number;
  pitch: number;
  volume: number;
  auto_play: boolean;
}

export interface AdminVoiceSettings extends VoiceSettings {
  allow_tenant_override: boolean;
  configured?: boolean; // tenant level: whether a tenant row exists
  updated_at?: string | null;
}

export interface EffectiveVoiceSettings extends VoiceSettings {
  source: "tenant" | "platform" | "builtin";
}
