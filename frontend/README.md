# Aurexion Chatbot — Frontend

React 18 + TypeScript + Vite + Tailwind CSS. Talks **only** to the chatbot Flask
backend at `/api/v1` (never to KMRAG). One login serves two experiences: an
**Admin Console** and a **Chat** workspace, gated by role.

## Quick start

```bash
npm install
cp .env.example .env         # VITE_API_TARGET -> Flask backend origin
npm run dev                  # http://127.0.0.1:5173
```

| Script | What it does |
|---|---|
| `npm run dev` | Vite dev server, proxies `/api` to the backend |
| `npm run build` | Type-check (`tsc --noEmit`) then production build to `dist/` |
| `npm run preview` | Serve the production build |
| `npm run test` | Vitest unit tests |
| `npm run lint` | Type-check only |

## Structure

```
src/
  api/            client.ts (axios + JWT refresh + error envelope), services.ts, types.ts
  context/        AuthContext (session), ToastContext (notifications)
  hooks/          useList (paginated+search lists), useAsync (single resource)
  components/
    ui/           primitives, Field, Modal, DataTable, Icons, StatusBadge
    layout/       AdminLayout (responsive sidebar + topbar)
    charts/       Charts (recharts wrappers, one shared palette)
    chat/         MessageBubble, SourceCard, NewChatModal
    common/       TenantPicker (super-admin tenant scoping)
  pages/
    LoginPage, ChatPage, NotFoundPage
    admin/        Dashboard, Tenants, KnowledgeBases, Documents, Users,
                  Conversations, Analytics, AuditLogs, Settings
  routes/         ProtectedRoute (auth + role gating)
```

## Behavior notes

- **Auth:** JWT access/refresh in `localStorage`; a 401 triggers a single-flight
  refresh, then a forced re-login if that fails. Roles route users to `/admin`
  (admins) or `/chat` (chat users).
- **Tenant scoping:** Super Admin gets a tenant picker on scoped screens; Tenant
  Admins are locked to their own tenant (never sent from the client as trusted).
- **Documents:** drag-and-drop upload with per-file progress. Status reflects the
  backend (documents sit at *Processing* — KMRAG is async with no completion
  signal). Delete is soft, and the UI says so.
- **Chat:** answers are labelled **General AI** vs **Knowledge Base**, with
  collapsible source cards (document, page, relevance). A **No Supporting
  Evidence** state is shown instead of guessing. Copy, retry, rename, delete,
  Enter-to-send / Shift+Enter newline.
- **Responsive:** desktop fixed sidebar → mobile drawer; tables scroll within
  their container; no horizontal page overflow.
- **Errors:** all surfaced through toasts / inline states using the backend's
  safe messages — no raw JSON or stack traces reach users.

The app is theme-consistent, accessible (focus rings, keyboard-dismissable
modals, semantic roles), and builds clean with code-split vendor chunks.
