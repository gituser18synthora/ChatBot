# Aurexion Chatbot Platform

A multi-tenant AI chatbot platform. It is a **standalone Flask + PostgreSQL + Redis**
service that uses the existing **`Synthora-AI-dev/kmrag`** service as an internal
RAG engine over HTTP. It answers general questions with OpenAI and
document-grounded questions with KMRAG, with full tenant isolation, RBAC, cost
tracking, and audit logging.

> **Status:** Complete. Flask backend (Phase 2) and the React + TypeScript
> frontend (Phase 3) are both implemented, tested, and verified end-to-end over
> HTTP. See [`frontend/README.md`](frontend/README.md) for the UI.

---

## 1. Architecture

```
                    ┌──────────────────────────────┐
  Admin Panel  ───► │                              │ ──► OpenAI  (general answers,
  Chat UI      ───► │   Chatbot Flask Backend      │      query classification,
   (React/TS)       │ (this repo, PostgreSQL+Redis)│      chat titles)
                    │                              │ ──► KMRAG /upload  (async ingest)
                    └──────────────────────────────┘ ──► KMRAG /query   (RAG answer+sources)
```

- The **frontend never calls KMRAG**. Only the Flask backend does, over HTTP.
- **PostgreSQL** is the source of truth for tenants, users, KBs (metadata), documents,
  chats, usage/cost, and audit logs.
- **Redis** is cache / rate-limit / JWT-revocation only — never source of truth.
- **KMRAG** owns OCR, parsing, chunking, embeddings, vector storage, retrieval,
  and grounded answer generation (Postgres + pgvector + Kafka). We never
  reimplement any of that.

### KMRAG contract (verified against `Synthora-AI-dev/kmrag/api/fast.py`)

| | Endpoint | Shape |
|---|---|---|
| Upload | `POST /upload?tenant_id=&kb_id=&kb_name=` (multipart `file`) | → `{status:"queued", kb_id, ...}` — **async via Kafka** |
| Query | `POST /query` (JSON) | → `{answer, request_id, metadata, upgrade_summary}` — **KMRAG returns the answer**; sources in `metadata.steps.retrieval.sources[]` |

The shared key across the boundary is `kb_id` (this backend generates the UUID
and passes it to KMRAG).

### Ingestion status (Processing → Indexed / Failed)

`/upload` is async (Kafka) and returns `queued` — KMRAG has no completion
callback. To resolve the status, a small **read-only endpoint was added to
KMRAG**: `GET /kb/{kb_id}/files?tenant_id=…` returns the files it has fully
ingested (a `kb_files` row exists) with chunk/token/cost stats. The chatbot
**reconciles** on every document-list load (and the UI auto-refreshes every 5s
while anything is in flight):

- file present in KMRAG → **Indexed** (`completed`), `processed_at` set;
- still absent after `DOCUMENT_PROCESSING_TIMEOUT_MINUTES` (default 30) →
  **Failed** with a clear message (retryable);
- a late-finishing job flips a timed-out **Failed** back to **Indexed**.

If KMRAG status can't be fetched (older KMRAG without the endpoint, or it's
unreachable), reconciliation is a no-op and documents stay `processing` — never
a crash. **⚠️ Restart the KMRAG service after pulling this change so it serves
`GET /kb/{kb_id}/files`** (added in `Synthora-AI-dev/kmrag/api/fast.py`); until
then documents will sit at Processing.

### Known limitations (imposed by the current KMRAG API — not by this code)
1. **No vector delete.** KMRAG exposes no delete endpoint, so document deletion
   is **soft-delete only** in PostgreSQL; the delete API response says so explicitly.
   *Future KMRAG endpoint needed:* delete document/vectors by `kb_id`+file.
2. **Sources lack `chunk_id`/`document_id`/preview.** KMRAG source rows carry
   `document_name, page_number, section, topic, score`. Those columns exist in
   our `chat_sources` table but stay NULL unless resolvable; we never fabricate.
3. **KMRAG-side token/cost** is captured only if present in the `/query`
   `metadata`; otherwise KMRAG-side cost is not invented (documented gap).
4. **Failure detail is timeout-based.** KMRAG doesn't persist per-file failures
   (failed jobs go to a Kafka DLQ), so "Failed" is inferred from the ingestion
   timeout rather than a specific KMRAG error reason.

---

## 2. Prerequisites

- Python 3.11+ (tested on 3.14)
- PostgreSQL 13+
- Redis 6+
- A running KMRAG service (from `Synthora-AI-dev`) reachable at `KMRAG_BASE_URL`
- An OpenAI API key

---

## 3. Backend setup

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then edit .env with real local values
```

### Database & Redis servers

The app needs a running **PostgreSQL** server and a **Redis** server. It creates
its own *database* and *schema* for you (next section) — you only need the server
and a role with the `CREATEDB` privilege.

```bash
redis-server        # or: sudo systemctl start redis
```

Set `POSTGRES_*` (or a full `DATABASE_URL`) and `REDIS_*` in `.env`. If the
PostgreSQL role you configure is not allowed to create databases, create the
database once by hand and the setup command will simply reuse it:

```sql
CREATE USER webuser WITH PASSWORD 'your_local_password';
CREATE DATABASE chatbot OWNER webuser;
GRANT ALL PRIVILEGES ON DATABASE chatbot TO webuser;
```

### Initialize the database — one command

After cloning, optionally set the first Super Admin credentials and run the setup
command. If you skip the credentials, a built-in default Super Admin is created
so you can log in immediately (**`admin@chatbot.local` / `Admin@123456`** — change
the password right after your first login):

```bash
export SEED_SUPERADMIN_EMAIL="admin@yourco.com"     # optional
export SEED_SUPERADMIN_PASSWORD="a-strong-password" # optional

flask --app run.py init-db          # or: python -m scripts.init_db
```

`init-db` runs the full bootstrap, and is **safe to run as many times as you
like**:

1. **Create database if missing** — checks `pg_database` and issues
   `CREATE DATABASE` only when absent (skips when it already exists; no-op on SQLite).
2. **Run all pending migrations** — `alembic upgrade head`, creating every
   table, primary key, foreign key, unique constraint and index. Already-applied
   migrations are skipped, so existing tables are never recreated or dropped.
3. **Verify** the schema is at the latest revision before finishing.
4. **Seed required default data** — the first Super Admin, inserted only when it
   does not already exist (from `SEED_SUPERADMIN_*`, or a built-in default when
   those are unset). This also runs automatically at startup when
   `DB_AUTO_UPGRADE=true`, so a fresh database is never left without a login.

Every step logs its progress (`DB_INIT step=…`), and a connection or migration
failure aborts with a clear, actionable message and a non-zero exit code.

Useful variants:

```bash
flask --app run.py init-db --no-seed          # schema only
flask --app run.py init-db --sample-tenant     # + local-dev sample tenant/KB
python -m scripts.init_db --sample-tenant      # same, without FLASK_APP set

flask --app run.py seed --super-admin          # (re)run just the Super Admin seed
flask --app run.py seed --sample-tenant        # local-dev fixtures only
```

Evolving the schema later still uses Flask-Migrate directly:
`flask db migrate -m "..."` then `flask db upgrade` (or just re-run `init-db`).

> **Schema always flows through Alembic migrations — never `db.create_all()`
> against a real database.** Creating tables outside Alembic leaves
> `alembic_version` behind and the schema half-applied, which surfaces later as
> confusing 500s. To help catch drift, the app checks the schema at boot:
> - default — logs a loud `DATABASE SCHEMA IS BEHIND` warning and boots anyway;
> - `DB_AUTO_UPGRADE=true` — creates-if-missing and runs migrations at startup
>   (handy for single-instance/dev; avoid with many concurrent workers, where
>   each worker must not migrate);
> - `DB_REQUIRE_CURRENT=true` — refuses to boot until the schema is current.
>
> `flask db check` reports any remaining model/schema drift.

### Run the backend

```bash
flask --app run.py run              # dev, http://127.0.0.1:5000
# or production:
gunicorn -w 4 -b 0.0.0.0:5000 "run:app"
```

### Run the tests

```bash
FLASK_ENV=testing python -m pytest -q
```
Tests use in-memory SQLite + `fakeredis` and **mock OpenAI and KMRAG** — no real
external calls are made.

---

## 4. Frontend setup (React + TypeScript)

```bash
cd frontend
npm install
cp .env.example .env        # VITE_API_TARGET points at the Flask backend
npm run dev                 # http://127.0.0.1:5173  (proxies /api to the backend)
```
Build & test:
```bash
npm run build               # type-checks then builds to dist/
npm run test                # vitest unit tests
npm run preview             # serve the production build
```
The dev server proxies `/api` to `VITE_API_TARGET` (default `http://127.0.0.1:5000`),
so the browser only ever talks to the backend — never to KMRAG. For production,
serve `frontend/dist` behind the same origin as the API (or set `VITE_API_BASE_URL`).

Two entry experiences share one login:
- **Admin Console** (`/admin`) — dashboard, tenants, knowledge bases, documents
  (drag-drop upload), users, conversations, usage & costs (charts), audit logs, settings.
  Super Admin sees all tenants; Tenant Admin is locked to their own.
- **Chat** (`/chat`) — new/rename/delete chats, KB multi-select, source cards,
  copy/retry, General-AI vs Knowledge-Base answer distinction. Fully responsive
  (drawer sidebar on mobile).

### Document upload — how it works & troubleshooting

The browser sends the file as `multipart/form-data` (field name `file`) to the
Flask backend, which validates it and forwards it to KMRAG. The frontend must
**not** set a `Content-Type` header for the upload — the browser sets
`multipart/form-data; boundary=…` itself (the axios client enforces this). A
successful upload returns `201` and the document shows **Processing** (KMRAG
ingests asynchronously and provides no completion signal — this is expected, not
a failure).

Every upload is logged with a correlation id. If uploads fail, check the backend
log:
- `upload received request_id=… file='…' size=…` then `upload queued …` → success.
- `upload rejected: no 'file' part. content_type='multipart/form-data' file_keys=[]`
  → the request had no boundary / wrong field name (a proxy or a non-browser client).
- `upload failed (kmrag) …` → KMRAG rejected/was unreachable; the document is
  marked **Failed** with a safe reason and can be retried.

Common causes and their (now-handled) behavior: file too large →
`413` with a clear message (raise `MAX_UPLOAD_FILE_SIZE_MB`); unsupported type →
`422` listing allowed extensions; too many uploads/min → `429` (raise
`RATE_LIMIT_UPLOAD_PER_MINUTE`, default 120); read-only `UPLOAD_TMP_DIR` → auto
fallback to the system temp dir. **After changing frontend code, rebuild
(`npm run build`) or restart `npm run dev` so the browser picks up the fix.**

## 5. API (base path `/api/v1`)

All responses use one envelope:
`{"success": true, "data": ...}` or `{"success": false, "error": {"code","message"}}`.
List endpoints add `meta: {page, per_page, total, pages}`. Send the JWT as
`Authorization: Bearer <token>`.

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/refresh` |
| Tenants (super admin) | `GET/POST /admin/tenants`, `GET/PUT/DELETE /admin/tenants/{id}` |
| Users (admins) | `GET/POST /users` (create accepts optional `kb_ids` for initial KB scoping), `GET/PUT /users/{id}`, `PATCH /users/{id}/status`, `DELETE /users/{id}` (soft), `GET/PUT /users/{id}/knowledge-bases` (per-user KB access) |
| Knowledge Bases | `GET/POST /tenants/{tid}/knowledge-bases`, `GET/PUT/DELETE /knowledge-bases/{id}`, `GET /tenants/{tid}/knowledge-bases/selectable` |
| Documents | `POST /knowledge-bases/{id}/documents/upload`, `GET /knowledge-bases/{id}/documents`, `GET/DELETE /documents/{id}`, `POST /documents/{id}/retry` |
| Chat | `GET /chat/knowledge-bases` (the signed-in user's effective KBs, with `document_count`/`indexed_count`/`ready`), `POST/GET /chat/sessions`, `GET/PUT/DELETE /chat/sessions/{id}`, `POST /chat/sessions/{id}/messages` (returns `assistant_message` + auto-generated `session_title`) |
| Profile (self-service) | `GET /profile`, `PUT /profile/tenant` (tenant admin: name/contact/`rag_mode`), `PUT /profile/password` |
| Analytics (admins) | `GET /analytics/dashboard`, `/costs`, `/tokens`, `/tenant/{id}`, `/knowledge-base/{id}` |
| Conversations (admins) | `GET /admin/conversations`, `GET /admin/conversations/{id}` |
| Super Tenant (Super User) | `GET /super-tenant`, `GET /super-tenant/knowledge-bases`, `GET/POST /super-tenant/knowledge-bases/{kb}/assignments`, `DELETE /super-tenant/knowledge-bases/{kb}/assignments/{tenant}` |
| Audit (admins) | `GET /audit-logs` |

### Sample calls

```bash
# Login
curl -s localhost:5000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@yourco.com","password":"..."}'

# Create a tenant (super admin)
curl -s localhost:5000/api/v1/admin/tenants -X POST \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"tenant_name":"Acme","tenant_code":"acme"}'

# Create a KB
curl -s localhost:5000/api/v1/tenants/$TID/knowledge-bases -X POST \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"kb_name":"Product Manuals"}'

# Upload a document (backend forwards to KMRAG internally)
curl -s localhost:5000/api/v1/knowledge-bases/$KBID/documents/upload -X POST \
  -H "Authorization: Bearer $TOKEN" -F "file=@manual.pdf"

# Start a chat scoped to a KB, then ask
curl -s localhost:5000/api/v1/chat/sessions -X POST \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "{\"title\":\"Docs\",\"kb_ids\":[\"$KBID\"]}"
curl -s localhost:5000/api/v1/chat/sessions/$SID/messages -X POST \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"message":"What does the uploaded manual say about warranty?"}'
```

---

## 6. Design notes

- **Tenant isolation** (`app/middleware/tenant_middleware.py`): Super Admin is
  cross-tenant; everyone else is locked to their own `tenant_id`, derived from
  the JWT — the frontend never supplies a trusted tenant id. Cross-tenant access
  returns `404` (no existence leak).
- **RBAC** (`app/middleware/auth_middleware.py`): `super_admin`, `tenant_admin`,
  `chat_user` via `require_roles(...)`.
- **Chat pipeline is retrieval-first** (`app/services/chat_service.py`): every
  message first checks the answer cache, then runs KMRAG retrieval whenever the
  user has a queryable KB — there is NO up-front intent classifier deciding
  "RAG vs general" (whether the KBs can answer is a property of their contents,
  which no phrasing-based router can know; that design skipped RAG for
  questions like "What is Acknowledgement Statement?"). Only when retrieval
  finds nothing does the mode-dependent fallback apply.
- **Answer cache** (`CHAT_ANSWER_CACHE_TTL_SECONDS`, default 1 h, 0 disables):
  an exact repeat of a question — same tenant, user, conversation, KB scope,
  models, and answering mode, query normalized (trim/lowercase/collapse
  whitespace) — is served from Redis with zero token cost, identical text, and
  its sources replayed. Keys are session-scoped so a cached answer can never
  leak across conversations, users, or tenants. Transient outcomes (KMRAG down
  or documents still indexing) are never cached. KMRAG's own exact/semantic
  answer caches also work now: the chatbot passes the **chat session id** as
  the KMRAG `request_id` (a per-HTTP-request id previously made those caches
  unable to ever hit, and broke KMRAG-side conversation history).
- **Chat step logs**: every message logs a greppable trace —
  `CHAT_REQUEST_RECEIVED`, `CACHE_LOOKUP … result=hit/miss`,
  `RAG_RETRIEVAL_STARTED`, `RAG_RETRIEVAL_RESULT total_hits=… vector_hits=…
  bm25_hits=…`, `RAG_CONTEXT_ATTACHED yes/no`, `LLM_FALLBACK_USED yes/no
  reason=…`, `CACHE_SAVE … status=success/skipped`,
  `CHAT_RESPONSE_COMPLETED source=cache/rag/fallback/no_evidence`.
- **Cost** (`app/services/cost_service.py`): pricing from `MODEL_PRICING_JSON`,
  computed at full `Decimal` precision, logged per call to `usage_logs`.
- **Redis keys** are always tenant-scoped, e.g. `tenant:{tid}:kb:{kb}`,
  `tenant:{tid}:rate_limit:{bucket}:{uid}`.
- **Errors** (`app/middleware/error_handler.py`): every exception becomes a clean
  JSON error; no traceback / SQL / KMRAG / OpenAI internals ever reach the client.

---

## 7. User roles & permissions

All users are rows in the PostgreSQL `users` table (`password_hash` via argon2). Role
ids are stable; the **`super_admin`** role is presented in the UI as **"Super
User"**. A Super User has `tenant_id = NULL` (platform-wide). The first one is
created by the seed script; after that Super Users create more users (any role)
from the **Users** screen. Roles are a JWT claim, enforced on every request by
`require_roles(...)` (RBAC) + the tenant-isolation guards.

Three roles (**Super User** logs into the admin console; **Tenant Admin** into
the admin console scoped to its tenant; **Chat User** — the "tenant login" — can
only reach the **chat** section):

| | **Super User** (`super_admin`) | **Tenant Admin** (`tenant_admin`) | **Chat User** (`chat_user`) |
|---|---|---|---|
| `tenant_id` | `NULL` (all tenants) | its tenant | its tenant |
| Access scope | **Every tenant** | **Only its own tenant** | **Chat section only** |
| Tenants | create / edit / activate / delete; designate the **Super Tenant** | — | — |
| Super Tenant panel (KB sharing) | **yes** | — | — |
| Knowledge bases | any tenant: CRUD | own tenant: CRUD | select owned + shared KBs in chat |
| Documents | upload / retry / delete anywhere | upload / retry / delete in own KBs | — |
| Users | create/manage **any** role in any tenant | create/manage **only `chat_user`** in own tenant | — |
| Conversations | view all (any tenant) | view own tenant | own chats only |
| Analytics / Costs | platform-wide + per tenant/KB/user | own tenant only | — |
| Audit logs | all | own tenant | — |
| Chat | — (no tenant; manages only) | general + document | general + document |

### Super Tenant & shared Knowledge Bases

Exactly one tenant can be flagged the **Super Tenant** (`tenants.is_super_tenant`).
Every tenant is **created as a normal tenant** — the create API/form deliberately
does not accept `is_super_tenant`; a Super User designates (or moves) the Super
Tenant afterwards from the tenant **Edit** dialog. The Super Tenant owns a
central KB library; from the **Super Tenant** panel the Super User assigns those
KBs to other tenants (`knowledge_base_assignments`). An assignment **grants
access** — the KB stays owned and ingested (in KMRAG) by the Super Tenant. At chat
time the backend authorizes the requesting tenant via the assignment table but
**queries KMRAG using the KB's owner (Super Tenant) tenant id**, since KMRAG
enforces retrieval isolation by owner. A chat's selectable KBs = the tenant's own
active KBs + KBs shared with it (marked "Shared" in the picker).

### Chat answering modes (per tenant): RAG-first vs RAG-only

Each tenant has a `rag_mode` (`tenants.rag_mode`) controlling how its chats answer:

Retrieval always runs first in both modes (when the user has a queryable KB);
the mode controls what happens when the Knowledge Bases have no answer:

- **`rag_first`** (default): falls back to a general-AI answer that explicitly
  discloses the information was not found in the organization's Knowledge Base
  and is instructed never to invent organization-specific facts.
- **`rag_only`**: general AI is disabled. When nothing relevant is found the
  bot answers *"I could not find this information in the assigned Knowledge
  Base(s)."*; when the user has no KB at all it answers *"No Knowledge Base is
  assigned to this user. Please contact your tenant admin."*

Who can change it: a **Tenant Admin** for their own tenant (Profile → “Chatbot
answering mode”), and a **Super User** for any tenant (Tenants → Edit).

### Per-user Knowledge Base access

A chat user's retrieval is scoped by `user_knowledge_base_assignments`:
**no rows = access to all** of the tenant's selectable KBs; one or more rows
restrict the user to exactly those KBs. Admins set this **when creating a user**
(KB checkboxes on the New User form) or later via the book icon on the Users
page (`GET/PUT /api/v1/users/{id}/knowledge-bases`). Enforcement is entirely
backend-side: session creation validates explicit picks
(`user_kb_service.assert_selectable`) and every message resolves the effective
KB set server-side — kb_ids from the client are never trusted.

### Automatic chat titles

New chats start as "New Chat"; after the **first user message** the backend
generates a short title from it (OpenAI `OPENAI_ROUTER_MODEL`, ≤ 6 words; on any
failure it falls back to a snippet of the message). The send-message response
includes `session_title` so the UI updates instantly. A manually renamed chat is
never re-titled.

### Soft-delete (tenants & users)

Deleting a **tenant** or a **user** is a **soft delete** — the row is retained for
audit/reference (`deleted_at` set), removed from active lists, and login is
blocked. Deleting a tenant also archives it (`status=inactive`) and deactivates
all its users so none can sign in. Nothing is permanently erased. (A soft-deleted
user's email stays reserved by the unique constraint — reuse would need a manual
DB step.) Permissions follow the role rules: a Super User can delete any tenant
or user (not self); a Tenant Admin can delete only Chat Users in their own tenant.

### Document deletion (removes vectors from KMRAG)

Deleting a document soft-deletes the record in PostgreSQL (kept for audit/reversibility)
**and** calls KMRAG `DELETE /kb/{kb_id}/files?tenant_id=&file_name=` (added in
`kmrag/api/fast.py`, wrapping KMRAG's existing `delete_chunks_by_file`) so its
chunks/embeddings are removed and it's excluded from retrieval. If KMRAG is
unreachable the soft-delete still applies (the doc is no longer queried) and the
API response says vector cleanup was unconfirmed — re-run delete when KMRAG is
back. **⚠️ Restart KMRAG after pulling this change so it serves the new
`DELETE /kb/{kb_id}/files` endpoint.**

Enforcement rules:
- The frontend **never** sends a trusted `tenant_id`; it is derived from the
  authenticated user. Super Admins may *select* a tenant to scope a view, which
  is validated server-side.
- A non-super-admin touching another tenant's resource gets **404** (not 403),
  so cross-tenant existence is never leaked.
- Tenant Admins can **only create Chat Users** (not Super Users or other Tenant
  Admins) and only in their own tenant; a user cannot change their own active
  status. Only a Super User can create Tenant Admins.

## 8. Environment variables

See [`backend/.env.example`](backend/.env.example) for the complete, commented
list. Never commit a real `.env`; `.env` is gitignored.
