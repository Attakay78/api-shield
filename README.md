<div align="center">
  <img src="api-shield-logo.svg" alt="API Shield" width=700/>
</div>


**Route lifecycle management for Python web frameworks — maintenance mode, environment gating, deprecation, admin panels, and more. No restarts required.**

Most "maintenance mode" tools are blunt instruments: shut everything down or nothing at all. `api-shield` treats each route as a first-class entity with its own lifecycle. State changes take effect immediately through middleware — no redeployment, no server restart.

---

## Contents

- [Adapters](#adapters)
  - [FastAPI](#fastapi)
    - [Installation](#installation)
    - [Quick Start](#quick-start)
    - [How It Works](#how-it-works)
    - [Decorators](#decorators)
    - [Dependency Injection](#dependency-injection)
    - [Global Maintenance Mode](#global-maintenance-mode)
    - [OpenAPI & Docs Integration](#openapi--docs-integration)
    - [Testing](#testing)
    - [Examples](#examples)
  - [Django — Coming Soon](#django--coming-soon)
  - [Flask — Coming Soon](#flask--coming-soon)
- [Backends](#backends)
  - [Custom Backends](#custom-backends)
- [Admin Interface](#admin-interface)
  - [Mounting ShieldAdmin](#mounting-shieldadmin)
  - [Authentication](#authentication)
  - [Dashboard UI](#dashboard-ui)
  - [REST API](#rest-api)
- [CLI Reference](#cli-reference)
  - [Authentication](#authentication-1)
  - [Route commands](#route-commands)
  - [Global maintenance commands](#global-maintenance-commands)
  - [Audit log](#audit-log-1)
  - [Config commands](#config-commands)
- [Audit Log](#audit-log)
- [Configuration File](#configuration-file)
- [Architecture](#architecture)
- [Error Response Format](#error-response-format)

---

## Adapters

### FastAPI

#### Installation

```bash
uv add api-shield
# or: pip install api-shield
```

For the full feature set:

```bash
uv add "api-shield[all]"
```

---

#### Quick Start

```python
from fastapi import FastAPI
from shield.core.config import make_engine
from shield.fastapi import (
    ShieldMiddleware,
    apply_shield_to_openapi,
    setup_shield_docs,
    maintenance,
    env_only,
    disabled,
    force_active,
    deprecated,
)

engine = make_engine()  # reads SHIELD_BACKEND, SHIELD_ENV, etc.

app = FastAPI(title="My API")
app.add_middleware(ShieldMiddleware, engine=engine)

@app.get("/payments")
@maintenance(reason="Database migration — back at 04:00 UTC")
async def get_payments():
    return {"payments": []}

@app.get("/health")
@force_active                        # always 200, immune to all shield checks
async def health():
    return {"status": "ok"}

@app.get("/debug")
@env_only("dev", "staging")         # silent 404 in production
async def debug():
    return {"debug": True}

@app.get("/old-endpoint")
@disabled(reason="Use /v2/endpoint")
async def old_endpoint():
    return {}

@app.get("/v1/users")
@deprecated(sunset="Sat, 01 Jan 2027 00:00:00 GMT", use_instead="/v2/users")
async def v1_users():
    return {"users": []}

apply_shield_to_openapi(app, engine) # filter /docs and /redoc
setup_shield_docs(app, engine)       # inject maintenance banners into UI
```

```
GET /payments      → 503  {"error": {"code": "MAINTENANCE_MODE", "reason": "..."}}
GET /health        → 200  always (force_active)
GET /debug         → 404  in production (env_only)
GET /old-endpoint  → 503  {"error": {"code": "ROUTE_DISABLED", "reason": "..."}}
GET /v1/users      → 200  + Deprecation/Sunset/Link response headers
```

---

#### How It Works

```
Incoming HTTP request
        │
        ▼
ShieldMiddleware.dispatch()
        │
        ├─ /docs, /redoc, /openapi.json  ──────────────────────→ pass through
        │
        ├─ Lazy-scan app routes for __shield_meta__ (once only)
        │
        ├─ @force_active route? ──────────────────────────────→ pass through
        │   (unless global maintenance overrides — see below)
        │
        ├─ engine.check(path, method)
        │       │
        │       ├─ Global maintenance ON + path not exempt? → 503
        │       ├─ MAINTENANCE  → 503 + Retry-After header
        │       ├─ DISABLED     → 503
        │       ├─ ENV_GATED    → 404 (silent — path existence not revealed)
        │       ├─ DEPRECATED   → pass through + inject response headers
        │       └─ ACTIVE       → pass through ✓
        │
        └─ call_next(request)
```

##### Route Registration

Shield decorators stamp `__shield_meta__` on the endpoint function. This metadata is registered with the engine at startup via two mechanisms:

1. **ASGI lifespan interception** — `ShieldMiddleware` hooks into `lifespan.startup.complete` to scan all app routes before the first request. This works with any `APIRouter` (plain or `ShieldRouter`).
2. **Lazy fallback** — on the first HTTP request if no lifespan was triggered (e.g. test environments).

State registration is **persistence-first**: if the backend already has a state for a route (written by a previous CLI command or earlier server run), the decorator default is ignored and the persisted state wins. This means runtime changes survive restarts.

---

#### Decorators

All decorators work on any router type — plain `APIRouter`, `ShieldRouter`, or routes added directly to the `FastAPI` app instance.

##### `@maintenance(reason, start, end)`

Puts a route into maintenance mode. Returns 503 with a structured JSON body. If `start`/`end` are provided, the maintenance window is also stored for scheduling.

```python
from shield.fastapi import maintenance
from datetime import datetime, UTC

@router.get("/payments")
@maintenance(reason="DB migration in progress")
async def get_payments():
    ...

# With a scheduled window
@router.post("/orders")
@maintenance(
    reason="Order system upgrade",
    start=datetime(2025, 6, 1, 2, 0, tzinfo=UTC),
    end=datetime(2025, 6, 1, 4, 0, tzinfo=UTC),
)
async def create_order():
    ...
```

Response:
```json
{
  "error": {
    "code": "MAINTENANCE_MODE",
    "message": "This endpoint is temporarily unavailable",
    "reason": "DB migration in progress",
    "path": "/payments",
    "retry_after": "2025-06-01T04:00:00Z"
  }
}
```

---

##### `@disabled(reason)`

Permanently disables a route. Returns 503. Use for routes that should never be called again (migrations, removed features).

```python
from shield.fastapi import disabled

@router.get("/legacy/report")
@disabled(reason="Replaced by /v2/reports — update your clients")
async def legacy_report():
    ...
```

---

##### `@env_only(*envs)`

Restricts a route to specific environment names. In any other environment the route returns a **silent 404** — it does not reveal that the path exists.

```python
from shield.fastapi import env_only

@router.get("/internal/metrics")
@env_only("dev", "staging")
async def internal_metrics():
    ...
```

The current environment is set via `SHIELD_ENV` or when constructing the engine:

```python
engine = ShieldEngine(current_env="production")
# or
engine = make_engine(current_env="staging")
```

---

##### `@force_active`

Bypasses all shield checks. Use for health checks, status endpoints, and any route that must always be reachable.

```python
from shield.fastapi import force_active

@router.get("/health")
@force_active
async def health():
    return {"status": "ok"}
```

`@force_active` routes are also **immune to runtime changes** — you cannot disable or put them in maintenance via the CLI or engine. This is intentional: health check routes must be trustworthy.

The only exception is when global maintenance mode is enabled with `include_force_active=True` (see [Global Maintenance Mode](#global-maintenance-mode)).

---

##### `@deprecated(sunset, use_instead)`

Marks a route as deprecated. Requests still succeed, but the middleware injects RFC-compliant response headers:

```python
from shield.fastapi import deprecated

@router.get("/v1/users")
@deprecated(
    sunset="Sat, 01 Jan 2027 00:00:00 GMT",
    use_instead="/v2/users",
)
async def v1_users():
    return {"users": []}
```

Response headers added automatically:
```
Deprecation: true
Sunset: Sat, 01 Jan 2027 00:00:00 GMT
Link: </v2/users>; rel="successor-version"
```

The route is also marked `deprecated: true` in the OpenAPI schema and shown with a visual indicator in `/docs`.

---

#### Global Maintenance Mode

Global maintenance blocks **every route** with a single call, without requiring per-route decorators. Use it for full deployments, infrastructure work, or emergency stops.

##### Programmatic (lifespan or runtime)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Enable global maintenance at startup
    await engine.enable_global_maintenance(
        reason="Scheduled deployment — back in 15 minutes",
        exempt_paths=["/health", "GET:/admin/status"],
        include_force_active=False,  # @force_active routes still bypass (default)
    )
    yield
    await engine.disable_global_maintenance()
```

Or toggle at runtime via any async context:

```python
# Enable — all non-exempt routes return 503 immediately
await engine.enable_global_maintenance(reason="Emergency patch")

# Disable — routes return to their per-route state
await engine.disable_global_maintenance()

# Check current state
cfg = await engine.get_global_maintenance()
print(cfg.enabled, cfg.reason, cfg.exempt_paths)

# Add/remove individual exemptions without toggling the mode
await engine.set_global_exempt_paths(["/health", "/status"])
```

##### Via CLI

```bash
# Enable with exemptions
shield global enable \
  --reason "Scheduled deployment" \
  --exempt /health \
  --exempt GET:/admin/status

# Block even force_active routes
shield global enable --reason "Hard lockdown" --include-force-active

# Add/remove exemptions while maintenance is already active
shield global exempt-add /monitoring/ping
shield global exempt-remove /monitoring/ping

# Check current state
shield global status

# Disable
shield global disable
```

##### Options

| Option | Default | Description |
|---|---|---|
| `reason` | `""` | Shown in every 503 response body |
| `exempt_paths` | `[]` | Bare paths (`/health`) or method-prefixed (`GET:/health`) |
| `include_force_active` | `False` | When `True`, `@force_active` routes are also blocked |

---

#### OpenAPI & Docs Integration

##### Schema filtering

```python
from shield.fastapi import apply_shield_to_openapi

apply_shield_to_openapi(app, engine)
```

Effect on `/docs` and `/redoc`:

| Route status | Schema behaviour |
|---|---|
| `DISABLED` | Hidden from all schemas |
| `ENV_GATED` (wrong env) | Hidden from all schemas |
| `MAINTENANCE` | Visible; operation summary prefixed with `🔧`; description shows warning block; `x-shield-status` extension added |
| `DEPRECATED` | Marked `deprecated: true`; successor path shown |
| `ACTIVE` | No change |

Schema is computed fresh on every request — runtime state changes (CLI, engine calls) reflect immediately without restarting.

---

##### Docs UI customisation

```python
from shield.fastapi import setup_shield_docs

apply_shield_to_openapi(app, engine)  # must come first
setup_shield_docs(app, engine)
```

Replaces both `/docs` and `/redoc` with enhanced versions:

**Global maintenance ON:**
- Full-width pulsing red sticky banner at the top of the page
- Reason text and exempt paths displayed
- Refreshes automatically every 15 seconds — no page reload needed

**Global maintenance OFF:**
- Small green "All systems operational" chip in the bottom-right corner

**Per-route maintenance:**
- Orange left-border on the operation block
- `🔧 MAINTENANCE` badge appended to the summary bar

---

#### Testing

```python
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from shield.core.backends.memory import MemoryBackend
from shield.core.engine import ShieldEngine
from shield.fastapi.decorators import maintenance, force_active
from shield.fastapi.middleware import ShieldMiddleware
from shield.fastapi.router import ShieldRouter


async def test_maintenance_returns_503():
    engine = ShieldEngine(backend=MemoryBackend())
    app = FastAPI()
    app.add_middleware(ShieldMiddleware, engine=engine)
    router = ShieldRouter(engine=engine)

    @router.get("/payments")
    @maintenance(reason="DB migration")
    async def get_payments():
        return {"ok": True}

    app.include_router(router)
    await app.router.startup()   # trigger shield route registration

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/payments")

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "MAINTENANCE_MODE"


async def test_runtime_enable_via_engine():
    engine = ShieldEngine(backend=MemoryBackend())

    await engine.set_maintenance("GET:/orders", reason="Upgrade")
    await engine.enable("GET:/orders")

    state = await engine.get_state("GET:/orders")
    assert state.status.value == "active"
```

`pyproject.toml` includes:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"   # all async tests work without @pytest.mark.asyncio
```

Run tests:

```bash
uv run pytest          # all tests
uv run pytest -v       # verbose
uv run pytest tests/fastapi/test_middleware.py   # specific file
uv run pytest tests/core/                        # core only (no FastAPI dependency)
```

---

#### Dependency Injection

Shield decorators double as FastAPI `Depends()` dependencies. This is useful when you want per-handler enforcement without adding `ShieldMiddleware`, or when running multiple engines in the same app.

`configure_shield(app, engine)` is called automatically by `ShieldMiddleware` at startup, so all deps resolve the engine from `app.state` with no extra configuration.

```python
from fastapi import Depends, FastAPI
from shield.fastapi import ShieldMiddleware, ShieldRouter, maintenance, disabled, env_only

app = FastAPI()
app.add_middleware(ShieldMiddleware, engine=engine)  # calls configure_shield automatically
router = ShieldRouter(engine=engine)

# Pattern A — middleware-only (decorator stamps metadata; middleware enforces globally)
@router.get("/payments")
@maintenance(reason="DB migration")
async def get_payments():
    return {"payments": []}

# Pattern B — Depends()-only (per-handler enforcement; no middleware required)
@router.get("/admin/report", dependencies=[Depends(disabled(reason="Use /v2/report"))])
async def admin_report():
    return {}

# Pattern C — both (most explicit; works with or without middleware)
@router.get(
    "/orders",
    dependencies=[Depends(maintenance(reason="Order upgrade"))],
)
@maintenance(reason="Order upgrade")
async def get_orders():
    return {"orders": []}

app.include_router(router)
```

**When to use each pattern:**

| Pattern | Best for |
|---|---|
| Decorator only | Apps that always run `ShieldMiddleware`; cleanest DX |
| `Depends()` only | Serverless / edge runtimes where middleware isn't available; fine-grained per-route control |
| Both | Library code or apps where callers may or may not use middleware |

All three patterns are runtime-togglable — use `shield enable /payments` or the dashboard without redeploying.

---

#### Examples

Runnable examples are in [examples/fastapi/](examples/fastapi/).

| File | What it demonstrates |
|---|---|
| [basic.py](examples/fastapi/basic.py) | Core decorators + `ShieldAdmin` (dashboard & CLI) |
| [dependency_injection.py](examples/fastapi/dependency_injection.py) | `Depends()` pattern alongside decorators + `ShieldAdmin` |
| [scheduled_maintenance.py](examples/fastapi/scheduled_maintenance.py) | Auto-activating maintenance windows via `schedule_maintenance()` |
| [global_maintenance.py](examples/fastapi/global_maintenance.py) | Blocking every route at once with `enable_global_maintenance()` |
| [custom_backend/sqlite_backend.py](examples/fastapi/custom_backend/sqlite_backend.py) | Full custom backend implementation using SQLite |

Run any example:

```bash
# Basic decorators + admin dashboard
uv run uvicorn examples.fastapi.basic:app --reload
# Then: http://localhost:8000/shield/  (login: admin / secret)

# Dependency injection + admin dashboard
uv run uvicorn examples.fastapi.dependency_injection:app --reload

# Scheduled maintenance window
uv run uvicorn examples.fastapi.scheduled_maintenance:app --reload

# Global maintenance mode
uv run uvicorn examples.fastapi.global_maintenance:app --reload

# SQLite custom backend (requires: pip install aiosqlite)
uv run uvicorn examples.fastapi.custom_backend.sqlite_backend:app --reload
```

---

### Django — Coming Soon

Django adapter is planned. It will provide:

- `ShieldMiddleware` as a standard Django middleware class
- Same decorators (`@maintenance`, `@disabled`, `@env_only`, `@deprecated`, `@force_active`) usable on Django views and DRF viewsets
- Integration with Django's URL routing for route registration at startup
- DRF schema filtering for `drf-spectacular` / `drf-yasg`

Track progress: [github.com/Attakay78/api-shield](https://github.com/Attakay78/api-shield)

---

### Flask — Coming Soon

Flask adapter is planned. It will provide:

- `ShieldMiddleware` as a WSGI/ASGI middleware compatible with Flask
- Same decorators usable on Flask route functions and Blueprints
- Integration with Flask's URL map for route registration at startup
- OpenAPI schema filtering for `flask-openapi3` / `flasgger`

Track progress: [github.com/Attakay78/api-shield](https://github.com/Attakay78/api-shield)

---

## Backends

The backend determines where route state and the audit log are persisted. Backends are shared across all adapters.

### `MemoryBackend` (default)

In-process dict. No persistence across restarts. CLI cannot share state with the running server.

```python
from shield.core.backends.memory import MemoryBackend
engine = ShieldEngine(backend=MemoryBackend())
```

Best for: development, single-process testing.

---

### `FileBackend`

JSON file on disk. Survives restarts. CLI shares state with the running server when both point to the same file.

```python
from shield.core.backends.file import FileBackend
engine = ShieldEngine(backend=FileBackend(path="shield-state.json"))
```

Or via environment variable:
```bash
SHIELD_BACKEND=file SHIELD_FILE_PATH=./shield-state.json uvicorn app:app
```

Best for: single-instance deployments, simple setups, CLI-driven workflows.

---

### `RedisBackend`

Redis via `redis-py` async. Supports multi-instance deployments. CLI changes reflect immediately on all running instances.

```python
from shield.core.backends.redis import RedisBackend
engine = ShieldEngine(backend=RedisBackend(url="redis://localhost:6379/0"))
```

Or via environment variable:
```bash
SHIELD_BACKEND=redis SHIELD_REDIS_URL=redis://localhost:6379/0 uvicorn app:app
```

Key schema:
- `shield:state:{path}` — route state
- `shield:audit` — audit log (LPUSH, capped at 1000 entries)
- `shield:global` — global maintenance configuration

Best for: multi-instance / load-balanced deployments, production.

---

### Custom Backends

Any storage layer can be used as a backend by subclassing `ShieldBackend` and implementing six async methods. api-shield handles everything else — the engine, middleware, decorators, CLI, and audit log all work unchanged.

#### Contract

```python
from shield.core.backends.base import ShieldBackend
from shield.core.models import AuditEntry, RouteState

class MyBackend(ShieldBackend):

    async def get_state(self, path: str) -> RouteState:
        # Return stored state. MUST raise KeyError if path not found.
        ...

    async def set_state(self, path: str, state: RouteState) -> None:
        # Persist state for path, overwriting any existing entry.
        ...

    async def delete_state(self, path: str) -> None:
        # Remove state for path. No-op if not found.
        ...

    async def list_states(self) -> list[RouteState]:
        # Return all registered route states.
        ...

    async def write_audit(self, entry: AuditEntry) -> None:
        # Append entry to the audit log.
        ...

    async def get_audit_log(
        self, path: str | None = None, limit: int = 100
    ) -> list[AuditEntry]:
        # Return audit entries newest-first, optionally filtered by path.
        ...
```

`subscribe()` is optional. The base class raises `NotImplementedError` by default, and the dashboard falls back to polling. Override it if your backend supports pub/sub.

#### Serialisation

`RouteState` and `AuditEntry` are Pydantic v2 models. Use their built-in helpers:

```python
# Serialise to a JSON string for storage
json_str = state.model_dump_json()

# Deserialise from a JSON string
state = RouteState.model_validate_json(json_str)
```

#### Rules

| Rule | Detail |
|---|---|
| `get_state()` must raise `KeyError` | The engine uses `KeyError` to distinguish "not registered" from "registered but active" |
| Fail-open on errors | Let exceptions bubble up — `ShieldEngine` wraps every backend call and allows requests through on failure |
| Thread safety | All methods are async; use your storage library's async client where available |
| Global maintenance | Inherited from `ShieldBackend` base class — no extra work needed unless you want a dedicated storage path |
| Lifecycle hooks | Override `startup()` / `shutdown()` for async setup/teardown — called automatically by `async with engine:` |

#### Wire the custom backend to the engine

```python
from shield.core.engine import ShieldEngine

backend = MyBackend()
engine  = ShieldEngine(backend=backend)
```

Use `async with engine:` to call `startup()` and `shutdown()` automatically:

```python
# FastAPI lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine:   # → backend.startup() … backend.shutdown()
        yield

app = FastAPI(lifespan=lifespan)
```

From there everything works as normal — decorators, middleware, CLI, audit log.

#### SQLite example

A complete working implementation backed by SQLite is in
[examples/fastapi/custom_backend/sqlite_backend.py](examples/fastapi/custom_backend/sqlite_backend.py).

Key points from that implementation:

```python
import aiosqlite
from shield.core.backends.base import ShieldBackend
from shield.core.models import AuditEntry, RouteState

class SQLiteBackend(ShieldBackend):
    def __init__(self, db_path: str = "shield-state.db") -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Open connection and create tables. Call at app startup."""
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS shield_states (
                path TEXT PRIMARY KEY, state_json TEXT NOT NULL
            )
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS shield_audit (
                id TEXT PRIMARY KEY, timestamp TEXT NOT NULL,
                path TEXT NOT NULL,  entry_json TEXT NOT NULL
            )
        """)
        await self._db.commit()

    async def get_state(self, path: str) -> RouteState:
        async with self._db.execute(
            "SELECT state_json FROM shield_states WHERE path = ?", (path,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            raise KeyError(path)           # ← required contract
        return RouteState.model_validate_json(row[0])

    async def set_state(self, path: str, state: RouteState) -> None:
        await self._db.execute(
            "INSERT INTO shield_states VALUES (?, ?)"
            " ON CONFLICT(path) DO UPDATE SET state_json = excluded.state_json",
            (path, state.model_dump_json()),
        )
        await self._db.commit()

    # ... delete_state, list_states, write_audit, get_audit_log
    # See the full file for the complete implementation.
```

Run the demo app:

```bash
pip install aiosqlite
uv run uvicorn examples.fastapi.custom_backend.sqlite_backend:app --reload
```

The `shield` CLI connects to the running app's `ShieldAdmin` REST API — no backend config needed on the CLI side:

```bash
shield login admin          # if auth is configured
shield status
shield disable GET:/payments --reason "patch"
shield log
```

---

## Admin Interface

`ShieldAdmin` is the single entry-point for the admin dashboard UI and the REST API used by the CLI. Mount it once on your FastAPI app to get both surfaces.

### Mounting ShieldAdmin

```python
from shield.admin import ShieldAdmin

app.mount(
    "/shield",
    ShieldAdmin(
        engine=engine,
        auth=("admin", "secret"),   # see Authentication below
        prefix="/shield",           # must match the mount path
        secret_key="stable-key",    # optional; omit in dev for random per-restart key
        token_expiry=86400,         # token lifetime in seconds (default 24 h)
    ),
)
```

### Authentication

`auth=` accepts three forms:

```python
# Single user
ShieldAdmin(engine=engine, auth=("admin", "secret"))

# Multiple users (each with their own credentials)
ShieldAdmin(engine=engine, auth=[("alice", "pass1"), ("bob", "pass2")])

# Custom backend — implement authenticate_user(username, password) -> bool
from shield.admin.auth import ShieldAuthBackend

class MyDBAuth(ShieldAuthBackend):
    def authenticate_user(self, username: str, password: str) -> bool:
        return self.db.check(username, password)

    # Optional — override to invalidate tokens when credentials change.
    # Default uses the class name (stable across restarts but not credential changes).
    def fingerprint(self) -> str:
        import hashlib
        rows = self.db.query("SELECT username, hash FROM users ORDER BY username")
        return hashlib.sha256("|".join(f"{u}:{h}" for u, h in rows).encode()).hexdigest()[:16]

ShieldAdmin(engine=engine, auth=MyDBAuth())

# No auth — open access (useful for internal tools or local dev)
ShieldAdmin(engine=engine)
```

**Token invalidation on credential change:** api-shield mixes a fingerprint of the `auth=` credentials into the HMAC signing key. When you change the `auth=` value (new user, changed password, different user entirely), all previously issued tokens are automatically invalidated on restart — even if `secret_key` is stable.

**`secret_key` guidance:**

| Environment | Recommendation |
|---|---|
| Development | Omit — random key generated on each restart; all sessions cleared on restart |
| Production | Set a stable value — tokens survive restarts; credential changes still invalidate via fingerprint |

### Dashboard UI

After mounting, the dashboard is available at your mount path:

```
http://localhost:8000/shield/         — route list with live status badges
http://localhost:8000/shield/audit    — audit log (newest first)
```

Browser sessions use `HttpOnly` cookies. The authenticated username is recorded as the `actor` in every audit log entry.

### REST API

The same mount exposes a JSON REST API used by the `shield` CLI:

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/auth/login` | Exchange credentials for a bearer token |
| `POST` | `/api/auth/logout` | Revoke the current token |
| `GET` | `/api/auth/me` | Current actor info |
| `GET` | `/api/routes` | List all route states |
| `GET` | `/api/routes/{key}` | Get one route |
| `POST` | `/api/routes/{key}/enable` | Enable a route |
| `POST` | `/api/routes/{key}/disable` | Disable a route |
| `POST` | `/api/routes/{key}/maintenance` | Put route in maintenance |
| `POST` | `/api/routes/{key}/schedule` | Schedule a maintenance window |
| `DELETE` | `/api/routes/{key}/schedule` | Cancel a scheduled window |
| `GET` | `/api/audit` | Audit log (supports `?route=` and `?limit=`) |
| `GET` | `/api/global` | Global maintenance config |
| `POST` | `/api/global/enable` | Enable global maintenance |
| `POST` | `/api/global/disable` | Disable global maintenance |

---

## CLI Reference

The `shield` CLI is a **thin HTTP client** — it talks to a running `ShieldAdmin` instance over HTTP. It does not touch the backend directly.

```bash
uv pip install "api-shield[cli]"
```

### Authentication

```bash
# Log in (prompts for password)
shield login admin

# Or pass credentials inline
shield login admin --password secret

# Check current session
shield config show

# Log out (revokes the server-side token and clears local credentials)
shield logout
```

Credentials are stored in `~/.shield/config.json` with an expiry timestamp. After expiry, re-run `shield login`.

### Server URL discovery

The CLI auto-discovers the server URL using this priority order (highest wins):

1. `SHIELD_SERVER_URL` environment variable
2. `SHIELD_SERVER_URL` key in a `.shield` file (walks up from cwd)
3. `server_url` in `~/.shield/config.json` (written by `shield config set-url`)
4. Built-in default: `http://localhost:8000/shield`

For most projects, dropping a `.shield` file in the repo root is enough — no manual URL configuration needed:

```ini
# .shield  (commit alongside your code)
SHIELD_SERVER_URL=http://localhost:8000/shield
```

### Route commands

```bash
shield status                           # all registered routes
shield status GET:/payments             # inspect one route

shield enable GET:/payments
shield disable GET:/payments --reason "Security patch"
shield disable GET:/payments --reason "hotfix" --until 2h   # auto re-enable in 2 h

shield maintenance GET:/payments --reason "DB swap"
shield maintenance GET:/payments \
  --reason "DB migration" \
  --start 2025-06-01T02:00Z \
  --end 2025-06-01T04:00Z

shield schedule GET:/payments \
  --start 2025-06-01T02:00Z \
  --end 2025-06-01T04:00Z \
  --reason "Planned migration"
```

### Global maintenance commands

```bash
shield global status
shield global enable --reason "Deploying v2" --exempt /health
shield global enable --reason "Hard lockdown" --include-force-active
shield global disable
shield global exempt-add /monitoring/ping
shield global exempt-remove /monitoring/ping
```

### Audit log

```bash
shield log                          # last 20 entries across all routes
shield log --route GET:/payments    # filter by route
shield log --limit 100
```

### Config commands

```bash
# Override the server URL (stored in ~/.shield/config.json)
shield config set-url http://prod.example.com/shield

# Show resolved URL + its source + current auth session
shield config show
```

### Route key format

Routes are stored with method-prefixed keys:

| What you type | What gets stored |
|---|---|
| `@router.get("/payments")` | `GET:/payments` |
| `@router.post("/payments")` | `POST:/payments` |
| `@router.get("/api/v1/users")` | `GET:/api/v1/users` |

```bash
shield disable "GET:/payments"
shield enable "/payments"           # applies to all methods registered under /payments
```

---

## Audit Log

Every state change writes an immutable audit entry:

```python
entries = await engine.get_audit_log(limit=50)
entries = await engine.get_audit_log(path="GET:/payments", limit=20)

for e in entries:
    print(e.timestamp, e.actor, e.platform, e.action, e.path,
          e.previous_status, "→", e.new_status, e.reason)
```

Fields: `id`, `timestamp`, `path`, `action`, `actor`, `platform`, `reason`, `previous_status`, `new_status`.

**Actor and platform are set automatically:**

| Source | `actor` | `platform` |
|---|---|---|
| CLI (logged in) | Authenticated username | `"cli"` |
| Dashboard (logged in) | Authenticated username | `"dashboard"` |
| No auth configured | Value of `X-Shield-Actor` header, or `"anonymous"` | `"cli"` / `"dashboard"` |

```bash
# After shield login admin:
shield disable GET:/payments --reason "Security patch"
# audit entry: actor="admin", platform="cli", action="disable", path="GET:/payments"
```

---

## Configuration File

Both the app and CLI auto-discover a `.shield` file by walking up from the current directory. Commit this alongside your code so the entire team shares the same settings with no manual setup.

```ini
# .shield
# ── App backend ───────────────────────────────────────────────────────────
SHIELD_BACKEND=file
SHIELD_FILE_PATH=shield-state.json
SHIELD_ENV=production

# ── CLI server URL ────────────────────────────────────────────────────────
# The CLI reads this so no one needs to run "shield config set-url ..."
SHIELD_SERVER_URL=http://localhost:8000/shield
```

**App backend priority order** (highest wins):
1. Explicit constructor argument (`ShieldEngine(backend=...)`)
2. `os.environ`
3. `.shield` file
4. Built-in defaults (`MemoryBackend`, `production` env)

**CLI server URL priority order** (highest wins):
1. `SHIELD_SERVER_URL` environment variable
2. `SHIELD_SERVER_URL` in `.shield` file (walked up from cwd)
3. `server_url` in `~/.shield/config.json` (written by `shield config set-url`)
4. Built-in default: `http://localhost:8000/shield`

---

## Architecture

```
shield/
├── core/                       # Framework-agnostic — zero framework imports
│   ├── models.py               # RouteState, AuditEntry, GlobalMaintenanceConfig
│   ├── engine.py               # ShieldEngine — all business logic
│   ├── scheduler.py            # MaintenanceScheduler (asyncio.Task based)
│   ├── config.py               # Backend/engine factory + .shield file loading
│   ├── exceptions.py           # MaintenanceException, EnvGatedException, ...
│   └── backends/
│       ├── base.py             # ShieldBackend ABC
│       ├── memory.py           # In-process dict
│       ├── file.py             # JSON file via aiofiles
│       └── redis.py            # Redis via redis-py async
│
├── fastapi/                    # FastAPI adapter
│   ├── middleware.py           # ShieldMiddleware (ASGI, BaseHTTPMiddleware)
│   ├── decorators.py           # @maintenance, @disabled, @env_only, ...
│   ├── router.py               # ShieldRouter + scan_routes()
│   └── openapi.py              # Schema filter + docs UI customisation
│
├── admin/                      # Unified admin interface
│   ├── app.py                  # ShieldAdmin factory — mounts dashboard + REST API
│   ├── api.py                  # REST API handlers (/api/routes, /api/audit, ...)
│   └── auth.py                 # TokenManager, ShieldAuthBackend, auth_fingerprint
│
├── dashboard/                  # HTMX dashboard UI (served via ShieldAdmin)
│   ├── routes.py               # Dashboard route handlers + SSE events
│   └── templates/              # Jinja2 templates (Tailwind + HTMX)
│
├── cli/                        # CLI — thin HTTP client over ShieldAdmin REST API
│   ├── main.py                 # Typer commands (login, status, enable, disable, ...)
│   ├── client.py               # ShieldClient (httpx-based)
│   └── config.py               # Config file + server URL auto-discovery
│
└── adapters/                   # Future framework adapters
    ├── django/                 # Coming soon
    └── flask/                  # Coming soon
```

### Request flow

```
CLI command                      Browser dashboard
     │                                  │
     │  HTTP + Bearer token             │  HTTP + HttpOnly cookie
     ▼                                  ▼
ShieldAdmin (mounted at /shield)
     ├── _AuthMiddleware  ─────────── inject actor + platform into request.state
     │
     ├── /api/...  ──────────────────  REST API handlers → ShieldEngine
     └── /  /audit /events  ─────────  Dashboard handlers → ShieldEngine
                                                  │
                                                  ▼
                                           ShieldBackend
                                    (memory / file / Redis / custom)
```

### Key design rules

1. **`shield.core` never imports from any adapter** — the core is framework-agnostic and powers all current and future adapters.
2. **All business logic lives in `ShieldEngine`** — middleware, decorators, API handlers, and CLI commands are transport layers. They call engine methods; they never make policy decisions themselves.
3. **`engine.check()` is the single chokepoint** — every request, regardless of framework or access surface, goes through this one method.
4. **Fail-open on backend errors** — if the backend is unreachable, requests pass through. Shield never takes down an API due to its own failures.
5. **Persistence-first registration** — if a route already has persisted state, the decorator default is ignored. Runtime changes survive restarts.
6. **Token invalidation on credential change** — the auth fingerprint is mixed into the HMAC signing key, so any change to `auth=` automatically invalidates all existing tokens even with a stable `secret_key`.

---

## Error Response Format

All shield-generated error responses follow a consistent JSON structure:

```json
{
  "error": {
    "code": "MAINTENANCE_MODE",
    "message": "This endpoint is temporarily unavailable",
    "reason": "Database migration in progress",
    "path": "/api/payments",
    "retry_after": "2025-06-01T04:00:00Z"
  }
}
```

| Scenario | HTTP status | `code` |
|---|---|---|
| Route in maintenance | 503 | `MAINTENANCE_MODE` |
| Route disabled | 503 | `ROUTE_DISABLED` |
| Route env-gated (wrong env) | 404 | *(no body — silent)* |
| Global maintenance active | 503 | `MAINTENANCE_MODE` |
