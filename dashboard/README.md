# EA Dashboard

Web UI for the AI Executive Assistant platform. Svelte 5 + TypeScript + Vite, served as static files by the FastAPI backend.

## Quick Start

```bash
# Dev mode (with Vite HMR + API proxy)
brew services start redis                         # if not already running
uv run python scripts/set_customer_secret.py cust_demo demo123
uv run python scripts/dev_server.py &             # lightweight backend on :8000
cd dashboard && npm install && npm run dev         # dashboard on :5173
```

Login at http://localhost:5173 with `cust_demo` / `demo123`.

```bash
# Production build (served by FastAPI)
cd dashboard && npm ci && npm run build            # outputs dist/
# FastAPI auto-detects dashboard/dist/ and mounts it at /
```

## Architecture

### Pages

| Route | Page | Data source |
|-------|------|-------------|
| `#/login` | Login form | `POST /v1/auth/login` |
| `#/overview` | Dashboard home | Real: conversations, notifications (peek). **Placeholder**: activity stats, specialist status |
| `#/conversations` | List + thread viewer | `GET /v1/conversations`, `GET /v1/conversations/:id/messages` |
| `#/configuration` | Working hours, briefing, proactive | `GET/PUT /v1/settings` |
| `#/personality` | Tone, language, EA name | `GET/PUT /v1/settings` |

### Key Decisions

**Custom hash router** (`src/lib/router.ts`, ~48 lines) — `svelte-spa-router` is incompatible with Svelte 5 (missing exports for runes mode). Routes use `#/path` format.

**In-memory token storage** — Token lives in a Svelte writable store, not localStorage. Prevents XSS extraction. Page refresh = re-login. Acceptable for MVP; revisit when adding refresh tokens.

**Non-destructive notifications** — Dashboard uses `GET /v1/notifications/peek` (reads without consuming). The existing `GET /v1/notifications` (destructive pop) remains for the WhatsApp flow.

**No component library** — CSS custom properties design system in `src/app.css`. Five pages don't justify a framework dependency.

### Backend Endpoints (added for dashboard)

- `POST /v1/auth/login` — Pre-shared key auth against Redis `customer_secret:{customer_id}`. Returns JWT. Uses `hmac.compare_digest` (constant-time). Same 401 for wrong secret and missing customer (no enumeration).
- `GET /v1/settings` — Returns `CustomerSettings` (all-null defaults if none saved). 200, never 404.
- `PUT /v1/settings` — Full replace semantics. Omitted fields reset to null.
- `GET /v1/notifications/peek` — Non-destructive read of pending notifications.

### Dev Server

`scripts/dev_server.py` — Lightweight FastAPI entrypoint that only needs Redis. Mocks out orchestrator, WhatsApp, and EA. Use this instead of `create_default_app` when you don't have Postgres/Docker/mem0 running.

Vite proxies `/v1`, `/healthz`, `/readyz`, `/webhook` to `localhost:8000` (see `vite.config.ts`).

## File Layout

```
dashboard/
  src/
    lib/
      api/client.ts          # Typed fetch wrapper (token inject, 401 redirect)
      api/types.ts            # TS interfaces matching Pydantic schemas
      auth/store.ts           # Svelte stores: token (memory), customerId, login(), logout()
      router.ts               # Hash-based SPA router (replaces svelte-spa-router)
    pages/                    # One component per route
    components/
      layout/                 # Shell, Sidebar, Header
      ui/                     # Card, Badge, Spinner, EmptyState
    app.css                   # CSS custom properties design system
    App.svelte                # Route table + auth guard
```

## What's Placeholder

Overview page has two sections with hardcoded mock data:
- **Activity summary** (message count, specialist delegations, proactive triggers) — waiting on `GET /v1/activity/today`
- **Specialist status** — waiting on `GET /v1/specialists/status`

These are marked with `// TODO` comments pointing to the endpoints they need.

## Tests

Backend tests in `tests/unit/api/`:
- `test_auth_login.py` — valid login, wrong secret, unknown customer, indistinguishable error responses, format validation
- `test_settings.py` — defaults, roundtrip, full-replace, tenant isolation, auth required, invalid tone
- `test_notifications.py` — peek returns data, peek doesn't consume, peek-then-pop lifecycle, auth required
