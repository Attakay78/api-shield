"""FastAPI — Multi-Service Switchly Server Example.

Demonstrates two independent FastAPI services (payments and orders) both
connecting to the same Switchly Server.  Each service registers its routes
under its own app_id namespace so the dashboard and CLI can manage them
independently or together.

This file defines THREE separate ASGI apps.  Run each in its own terminal:

  Switchly Server (port 8001):
    uv run --with uvicorn uvicorn examples.fastapi.multi_service:switchly_app --port 8001 --reload

  Payments service (port 8000):
    uv run --with uvicorn uvicorn examples.fastapi.multi_service:payments_app --port 8000 --reload

  Orders service (port 8002):
    uv run --with uvicorn uvicorn examples.fastapi.multi_service:orders_app --port 8002 --reload

Then visit:
    http://localhost:8001/           — Switchly dashboard (admin / secret)
                                       Use the service dropdown to switch between
                                       "payments-service" and "orders-service"
    http://localhost:8000/docs       — Payments Swagger UI
    http://localhost:8002/docs       — Orders Swagger UI

CLI — points at the Switchly Server; use --service or SWITCHLY_SERVICE to scope:

    # One-time setup
    switchly config set-url http://localhost:8001
    switchly login admin              # password: secret

    # View all registered services
    switchly services

    # Manage payments routes
    export SWITCHLY_SERVICE=payments-service
    switchly status
    switchly disable /api/payments --reason "hotfix"
    switchly enable  /api/payments

    # Switch to orders without changing env var
    switchly status --service orders-service

    # Explicit --service flag overrides the env var
    export SWITCHLY_SERVICE=payments-service
    switchly enable /api/orders --service orders-service

    # Clear the env var to work across all services at once
    unset SWITCHLY_SERVICE
    switchly status                   # shows routes from both services
    switchly audit                    # audit log from both services

    # Global maintenance — affects ALL services
    switchly global disable --reason "emergency maintenance"
    switchly global enable

Expected behaviour:
    Payments (port 8000):
        GET /health            → 200 always               (@force_active)
        GET /api/payments      → 503 MAINTENANCE_MODE     (starts in maintenance)
        GET /api/refunds       → 200                      (active)
        GET /api/v1/invoices   → 200 + deprecation hdr    (@deprecated)
        GET /api/v2/invoices   → 200                      (active successor)

    Orders (port 8002):
        GET /health            → 200 always               (@force_active)
        GET /api/orders        → 200                      (active)
        GET /api/shipments     → 503 ROUTE_DISABLED       (@disabled)
        GET /api/cart          → 200                      (active)

Production notes:
    Backend choice affects the Switchly Server only.  All SDK clients receive
    live SSE updates regardless of backend — they connect to the Switchly Server
    over HTTP, never to the backend directly:

    * MemoryBackend  — fine for development; state lost on Switchly Server restart.
    * FileBackend    — state survives restarts; single Switchly Server instance only.
    * RedisBackend   — needed only when running multiple Switchly Server instances
                       (HA / load-balanced). Redis pub/sub keeps all nodes in
                       sync so every SDK client sees consistent state.

    * Use a stable secret_key so tokens survive Switchly Server restarts.
    * Prefer passing username/password to each SwitchlySDK so each service
      obtains its own sdk-platform token on startup automatically.
    * Set token_expiry (dashboard/CLI) and sdk_token_expiry (services)
      independently so human sessions stay short-lived.
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
    setup_switchly_docs,
)
from switchly.sdk import SwitchlySDK
from switchly.server import SwitchlyServer

# ---------------------------------------------------------------------------
# Switchly Server — shared by all services
# ---------------------------------------------------------------------------
# Run: uv run uvicorn examples.fastapi.multi_service:switchly_app --port 8001 --reload
#
# All services register their routes here.  The dashboard service dropdown
# lets you filter and manage each service independently.
#
# For production: swap MemoryBackend for RedisBackend:
#   from switchly import RedisBackend
#   backend = RedisBackend("redis://localhost:6379")

switchly_app = SwitchlyServer(
    backend=MemoryBackend(),
    auth=("admin", "secret"),
    # secret_key="change-me-in-production",
    # token_expiry=3600,          # dashboard / CLI sessions — default 24 h
    # sdk_token_expiry=31536000,  # SDK service tokens — default 1 year
)

# ---------------------------------------------------------------------------
# Payments Service (port 8000)
# ---------------------------------------------------------------------------
# Run: uv run uvicorn examples.fastapi.multi_service:payments_app --port 8000 --reload
#
# app_id="payments-service" namespaces all routes from this service on the
# Switchly Server.  The dashboard shows them separately from orders-service.
# CLI: export SWITCHLY_SERVICE=payments-service; switchly status

payments_sdk = SwitchlySDK(
    server_url="http://localhost:8001",
    app_id="payments-service",
    username="admin",
    password="secret",
    # Auto-login (recommended): SDK obtains a 1-year sdk-platform token on startup.
    # username="admin",   # inject from env: os.environ["SWITCHLY_USERNAME"]
    # password="secret",  # inject from env: os.environ["SWITCHLY_PASSWORD"]
    # Or use a pre-issued token: token=os.environ["SWITCHLY_TOKEN"]
    reconnect_delay=5.0,
)

payments_app = FastAPI(
    title="switchly — Payments Service",
    description=(
        "Connects to the Switchly Server at **http://localhost:8001** as "
        "`payments-service`.  Manage routes from the "
        "[Switchly Dashboard](http://localhost:8001/) or via the CLI with "
        "`export SWITCHLY_SERVICE=payments-service`."
    ),
)

payments_sdk.attach(payments_app)

payments_router = SwitchlyRouter(engine=payments_sdk.engine)


@payments_router.get("/health")
@force_active
async def payments_health():
    """Always 200 — load-balancer probe endpoint."""
    return {"status": "ok", "service": "payments-service"}


@payments_router.get("/api/payments")
@maintenance(reason="Payment processor upgrade — back at 04:00 UTC")
async def process_payment():
    """Returns 503 MAINTENANCE_MODE on startup.

    Restore from the CLI:
        export SWITCHLY_SERVICE=payments-service
        switchly enable /api/payments
    """
    return {"payment_id": "pay_abc123", "status": "processed"}


@payments_router.get("/api/refunds")
async def list_refunds():
    """Active on startup.

    Disable from the CLI:
        switchly disable /api/refunds --reason "audit in progress" \\
               --service payments-service
    """
    return {"refunds": [{"id": "ref_001", "amount": 49.99}]}


@payments_router.get("/api/v1/invoices")
@deprecated(sunset="Sat, 01 Jun 2028 00:00:00 GMT", use_instead="/api/v2/invoices")
async def v1_invoices():
    """Returns 200 with Deprecation, Sunset, and Link response headers."""
    return {"invoices": [{"id": "inv_001", "total": 199.99}], "version": 1}


@payments_router.get("/api/v2/invoices")
async def v2_invoices():
    """Active successor to /api/v1/invoices."""
    return {"invoices": [{"id": "inv_001", "total": 199.99}], "version": 2}


payments_app.include_router(payments_router)
apply_switchly_to_openapi(payments_app, payments_sdk.engine)
setup_switchly_docs(payments_app, payments_sdk.engine)

# ---------------------------------------------------------------------------
# Orders Service (port 8002)
# ---------------------------------------------------------------------------
# Run: uv run uvicorn examples.fastapi.multi_service:orders_app --port 8002 --reload
#
# app_id="orders-service" gives this service its own namespace on the server.
# CLI: export SWITCHLY_SERVICE=orders-service; switchly status

orders_sdk = SwitchlySDK(
    server_url="http://localhost:8001",
    app_id="orders-service",
    username="admin",
    password="secret",
    # Auto-login (recommended): SDK obtains a 1-year sdk-platform token on startup.
    # username="admin",   # inject from env: os.environ["SWITCHLY_USERNAME"]
    # password="secret",  # inject from env: os.environ["SWITCHLY_PASSWORD"]
    # Or use a pre-issued token: token=os.environ["SWITCHLY_TOKEN"]
    reconnect_delay=5.0,
)

orders_app = FastAPI(
    title="switchly — Orders Service",
    description=(
        "Connects to the Switchly Server at **http://localhost:8001** as "
        "`orders-service`.  Manage routes from the "
        "[Switchly Dashboard](http://localhost:8001/) or via the CLI with "
        "`export SWITCHLY_SERVICE=orders-service`."
    ),
)

orders_sdk.attach(orders_app)

orders_router = SwitchlyRouter(engine=orders_sdk.engine)


@orders_router.get("/health")
@force_active
async def orders_health():
    """Always 200 — load-balancer probe endpoint."""
    return {"status": "ok", "service": "orders-service"}


@orders_router.get("/api/orders")
async def list_orders():
    """Active on startup.

    Disable from the CLI:
        switchly disable /api/orders --reason "inventory sync" \\
               --service orders-service
    """
    return {"orders": [{"id": 42, "status": "shipped"}]}


@orders_router.get("/api/shipments")
@disabled(reason="Shipment provider integration deprecated — use /api/orders")
async def list_shipments():
    """Returns 503 ROUTE_DISABLED.

    Re-enable from the CLI if you need to temporarily restore access:
        switchly enable /api/shipments --service orders-service
    """
    return {}


@orders_router.get("/api/cart")
async def get_cart():
    """Active on startup.

    Put the whole orders-service in global maintenance from the dashboard
    or pause just this route:
        switchly maintenance /api/cart --reason "cart redesign" \\
               --service orders-service
    """
    return {"cart": {"items": [], "total": 0.0}}


orders_app.include_router(orders_router)
apply_switchly_to_openapi(orders_app, orders_sdk.engine)
setup_switchly_docs(orders_app, orders_sdk.engine)

# ---------------------------------------------------------------------------
# CLI reference — multi-service workflow
# ---------------------------------------------------------------------------
#
# Setup (once):
#   switchly config set-url http://localhost:8001
#   switchly login admin
#
# View all services and their routes:
#   switchly services
#   switchly status                           # routes from ALL services combined
#
# Scope to a specific service via env var:
#   export SWITCHLY_SERVICE=payments-service
#   switchly status                           # only payments-service routes
#   switchly disable /api/payments --reason "hotfix"
#   switchly enable  /api/payments
#   switchly maintenance /api/refunds --reason "audit"
#
# Switch service without changing the env var (--service flag):
#   switchly status --service orders-service
#   switchly disable /api/orders --reason "inventory sync" \\
#          --service orders-service
#
# Explicit flag always overrides the SWITCHLY_SERVICE env var:
#   export SWITCHLY_SERVICE=payments-service
#   switchly enable /api/orders --service orders-service   # acts on orders
#
# Unscoped commands operate across all services:
#   unset SWITCHLY_SERVICE
#   switchly audit                            # audit log from both services
#   switchly global disable --reason "emergency maintenance"
#   switchly global enable
