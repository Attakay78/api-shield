"""FastAPI — Switchly Server Mode Example.

Demonstrates the centralized Switchly Server architecture: a single Switchly
Server process owns all route state, and one or more service apps connect
to it via SwitchlySDK.  State is enforced locally on every request with zero
network overhead — the SDK keeps an in-process cache synced over a
persistent SSE connection.

This file defines TWO separate ASGI apps.  Run them in separate terminals:

  App 1 — The Switchly Server (port 8001):
    uv run uvicorn examples.fastapi.switchly_server:switchly_app --port 8001 --reload

  App 2 — The Service App (port 8000):
    uv run uvicorn examples.fastapi.switchly_server:service_app --port 8000 --reload

Then visit:
    http://localhost:8001/           — Switchly Server dashboard (admin / secret)
    http://localhost:8001/audit      — audit log (all services)
    http://localhost:8000/docs       — service Swagger UI

CLI — always points at the Switchly Server, not the service:
    switchly config set-url http://localhost:8001
    switchly login admin              # password: secret
    switchly status                   # routes registered by my-service
    switchly disable /api/orders --reason "hotfix"
    switchly enable /api/orders
    switchly maintenance /api/payments --reason "DB migration"
    switchly audit                    # full audit trail

Expected behaviour:
    GET /health          → 200 always              (@force_active — survives disable)
    GET /api/payments    → 503 MAINTENANCE_MODE    (starts in maintenance)
    GET /api/orders      → 200                     (active on startup)
    GET /api/legacy      → 503 ROUTE_DISABLED      (@disabled)
    GET /api/v1/products → 200 + deprecation hdr   (@deprecated)
    GET /api/v2/products → 200                     (active successor)

Production notes:
    Backend choice affects the Switchly Server only — SDK clients always receive
    live SSE updates regardless of backend, because they connect to the Switchly
    Server over HTTP (not to the backend directly):

    * MemoryBackend  — fine for development; state is lost when the Switchly
                       Server restarts.
    * FileBackend    — state survives restarts; safe for single-server
                       deployments (no multi-process file locking).
    * RedisBackend   — required only when you run multiple Switchly Server
                       instances behind a load balancer (high availability).
                       Cross-instance pub/sub keeps all Switchly Server nodes
                       in sync so every SDK client gets consistent state.

    * Use a stable secret_key so tokens survive Switchly Server restarts.
    * Prefer passing username/password to SwitchlySDK so the SDK obtains its
      own sdk-platform token on startup (sdk_token_expiry, default 1 year)
      rather than managing a pre-issued token manually.
    * Set token_expiry (dashboard/CLI sessions) and sdk_token_expiry (service
      tokens) independently so human sessions stay short-lived.
"""

from __future__ import annotations

from fastapi import FastAPI

from switchly import MemoryBackend
from switchly.fastapi import (
    SwitchlyRouter,
    apply_switchly_to_openapi,
    deprecated,
    disabled,
    force_active,
    maintenance,
)
from switchly.sdk import SwitchlySDK
from switchly.server import SwitchlyServer

# ---------------------------------------------------------------------------
# App 1 — Switchly Server
# ---------------------------------------------------------------------------
# Run: uv run uvicorn examples.fastapi.switchly_server:switchly_app --port 8001 --reload
#
# The Switchly Server is a self-contained ASGI app that exposes:
#   /            — HTMX dashboard UI  (login: admin / secret)
#   /audit       — audit log
#   /api/...     — REST API consumed by the CLI
#   /api/sdk/... — SSE + register endpoints consumed by SwitchlySDK clients
#
# For production: swap MemoryBackend for RedisBackend so every connected
# service receives live state updates via the SSE channel.
#
#   from switchly import RedisBackend
#   backend = RedisBackend("redis://localhost:6379")
#
# secret_key should be a stable value so issued tokens survive restarts.
# Omit it (or pass None) in development — a random key is generated per run.

switchly_app = SwitchlyServer(
    backend=MemoryBackend(),
    auth=("admin", "secret"),
    # secret_key="change-me-in-production",
    # token_expiry=3600,       # dashboard / CLI sessions — default 24 h
    # sdk_token_expiry=31536000,  # SDK service tokens — default 1 year
)

# ---------------------------------------------------------------------------
# App 2 — Service App
# ---------------------------------------------------------------------------
# Run: uv run uvicorn examples.fastapi.switchly_server:service_app --port 8000 --reload
#
# SwitchlySDK wires SwitchlyMiddleware + startup/shutdown lifecycle into the app.
# Route enforcement is purely local — the SDK never adds per-request latency.
#
# Authentication options (choose one):
#
#   1. Auto-login — recommended for production. The SDK calls
#      POST /api/auth/login with platform="sdk" on startup and caches the
#      returned token (valid for sdk_token_expiry, default 1 year).
#      Inject credentials from environment variables:
#
#        sdk = SwitchlySDK(
#            server_url="http://localhost:8001",
#            app_id="my-service",
#            username=os.environ["SWITCHLY_USERNAME"],
#            password=os.environ["SWITCHLY_PASSWORD"],
#        )
#
#   2. Pre-issued token — obtain once via `switchly login`, store as a secret:
#        sdk = SwitchlySDK(..., token=os.environ["SWITCHLY_TOKEN"])
#
#   3. No auth — omit token/username/password when the Switchly Server has
#      no auth configured (auth=None or auth omitted).

sdk = SwitchlySDK(
    server_url="http://localhost:8001",
    app_id="my-service",
    username="admin",
    password="secret",
    # username="admin",   # or inject from env: os.environ["SWITCHLY_USERNAME"]
    # password="secret",  # or inject from env: os.environ["SWITCHLY_PASSWORD"]
    reconnect_delay=5.0,  # seconds between SSE reconnect attempts
)

service_app = FastAPI(
    title="switchly — Switchly Server Example (Service)",
    description=(
        "Connects to the Switchly Server at **http://localhost:8001** via "
        "SwitchlySDK.  All route state is managed centrally — use the "
        "[Switchly Dashboard](http://localhost:8001/) or the CLI to "
        "enable, disable, or pause any route without redeploying."
    ),
)

# attach() adds SwitchlyMiddleware and wires startup/shutdown hooks.
# Call this BEFORE defining routes so the router below can use sdk.engine.
sdk.attach(service_app)

# SwitchlyRouter auto-registers decorated routes with the Switchly Server on
# startup so they appear in the dashboard immediately.
router = SwitchlyRouter(engine=sdk.engine)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/health")
@force_active
async def health():
    """Always 200 — bypasses every switchly check.

    Use this for load-balancer probes.  @force_active ensures the route
    stays reachable even if the Switchly Server is temporarily unreachable
    and the SDK falls back to its empty local cache.
    """
    return {"status": "ok", "service": "my-service"}


@router.get("/api/payments")
@maintenance(reason="Scheduled database migration — back at 04:00 UTC")
async def get_payments():
    """Returns 503 MAINTENANCE_MODE on startup.

    Lift maintenance from the CLI (no redeploy needed):
        switchly enable /api/payments
    """
    return {"payments": [{"id": 1, "amount": 99.99}]}


@router.get("/api/orders")
async def list_orders():
    """Active on startup — disable from the CLI:

    switchly disable /api/orders --reason "hotfix"
    switchly enable  /api/orders
    """
    return {"orders": [{"id": 42, "status": "shipped"}]}


@router.get("/api/legacy")
@disabled(reason="Use /api/v2/products instead")
async def legacy_endpoint():
    """Returns 503 ROUTE_DISABLED.

    The @disabled state is set at deploy time and can be overridden from
    the dashboard or CLI:
        switchly enable /api/legacy
    """
    return {}


@router.get("/api/v1/products")
@deprecated(sunset="Sat, 01 Jan 2028 00:00:00 GMT", use_instead="/api/v2/products")
async def v1_products():
    """Returns 200 with Deprecation, Sunset, and Link response headers.

    Headers injected by SwitchlyMiddleware on every response:
        Deprecation: true
        Sunset: Sat, 01 Jan 2028 00:00:00 GMT
        Link: </api/v2/products>; rel="successor-version"
    """
    return {"products": [{"id": 1, "name": "Widget"}], "version": 1}


@router.get("/api/v2/products")
async def v2_products():
    """Active successor to /api/v1/products."""
    return {"products": [{"id": 1, "name": "Widget"}], "version": 2}


service_app.include_router(router)
apply_switchly_to_openapi(service_app, sdk.engine)

# ---------------------------------------------------------------------------
# How the CLI talks to this setup
# ---------------------------------------------------------------------------
#
# The CLI always communicates with the Switchly Server, never directly with
# the service app.  From the Switchly Server's perspective, routes from
# "my-service" appear namespaced as "my-service:/api/payments" etc.
#
#   # One-time setup
#   switchly config set-url http://localhost:8001
#   switchly login admin
#
#   # Inspect state
#   switchly status                               # all routes for my-service
#   switchly audit                                # full audit trail
#
#   # Lifecycle management
#   switchly disable /api/orders --reason "hotfix"
#   switchly enable  /api/orders
#   switchly maintenance /api/payments --reason "scheduled downtime"
#   switchly schedule /api/payments               # set maintenance window
#
#   # Dashboard
#   open http://localhost:8001/                 # full UI, no CLI needed
