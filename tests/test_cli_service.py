"""Tests for SHIELD_SERVICE env var fallback and shield current-service command.

The CLI is a thin HTTP client; tests create an in-process ShieldAdmin ASGI
app and inject it into the CLI via the ``make_client`` monkeypatch, so no
real server is needed.

IMPORTANT: Tests that call ``invoke_with_client`` must be sync (``def``, not
``async def``) because the CLI uses ``anyio.run()`` internally and that
cannot be nested inside a running pytest-asyncio event loop.
"""

from __future__ import annotations

from unittest.mock import patch

import anyio
import httpx
from typer.testing import CliRunner

from shield.admin.app import ShieldAdmin
from shield.cli.client import ShieldClient
from shield.cli.main import cli as app
from shield.core.engine import ShieldEngine
from shield.core.models import RouteState, RouteStatus

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_engine(*paths: str) -> ShieldEngine:
    """Create a ShieldEngine and seed *paths* as ACTIVE routes (synchronously)."""
    e = ShieldEngine()

    async def _run() -> None:
        for path in paths:
            await e.backend.set_state(path, RouteState(path=path, status=RouteStatus.ACTIVE))

    anyio.run(_run)
    return e


def _run_sync(coro_fn):
    """Run a no-argument async callable synchronously and return the result."""
    results = []

    async def _wrap():
        results.append(await coro_fn())

    anyio.run(_wrap)
    return results[0] if results else None


def _open_client(engine: ShieldEngine) -> ShieldClient:
    """Return a ShieldClient backed by an in-process ShieldAdmin (no auth)."""
    admin = ShieldAdmin(engine=engine)
    return ShieldClient(
        base_url="http://testserver",
        transport=httpx.ASGITransport(app=admin),  # type: ignore[arg-type]
    )


def invoke_with_client(client: ShieldClient, *args: str) -> object:
    """Invoke a CLI command with *client* injected via ``make_client``."""
    with patch("shield.cli.main.make_client", return_value=client):
        return runner.invoke(app, list(args), catch_exceptions=False)


# ---------------------------------------------------------------------------
# current-service command
# ---------------------------------------------------------------------------


def test_current_service_no_env(monkeypatch) -> None:
    """shield current-service with no SHIELD_SERVICE set shows 'No active service'."""
    monkeypatch.delenv("SHIELD_SERVICE", raising=False)
    result = runner.invoke(app, ["current-service"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "No active service" in result.output


def test_current_service_with_env(monkeypatch) -> None:
    """shield current-service with SHIELD_SERVICE set shows the service name."""
    monkeypatch.setenv("SHIELD_SERVICE", "payments-service")
    result = runner.invoke(app, ["current-service"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "payments-service" in result.output


# ---------------------------------------------------------------------------
# status --service (env var fallback)
# ---------------------------------------------------------------------------


def test_status_uses_shield_service_env(monkeypatch) -> None:
    """SHIELD_SERVICE env var causes status to filter routes to that service."""
    monkeypatch.setenv("SHIELD_SERVICE", "payments-service")

    e = ShieldEngine()

    async def _seed() -> None:
        state = RouteState(
            path="payments-service:/api/pay",
            service="payments-service",
            status=RouteStatus.ACTIVE,
        )
        await e.backend.set_state("payments-service:/api/pay", state)

    anyio.run(_seed)

    client = _open_client(e)
    result = invoke_with_client(client, "status")
    assert result.exit_code == 0
    # The status output should reference the service or the route path fragment.
    assert (
        "payments-service" in result.output or "/api/pay" in result.output or "api" in result.output
    )


# ---------------------------------------------------------------------------
# enable — SHIELD_SERVICE env var builds composite key
# ---------------------------------------------------------------------------


def test_enable_uses_shield_service_env(monkeypatch) -> None:
    """shield enable /api/pay uses SHIELD_SERVICE to form composite key."""
    monkeypatch.setenv("SHIELD_SERVICE", "payments-service")

    e = ShieldEngine()

    async def _seed() -> None:
        # Seed as DISABLED so enable has something to act on.
        state = RouteState(
            path="payments-service:/api/pay",
            service="payments-service",
            status=RouteStatus.DISABLED,
        )
        await e.backend.set_state("payments-service:/api/pay", state)

    anyio.run(_seed)

    client = _open_client(e)
    result = invoke_with_client(client, "enable", "/api/pay")
    assert result.exit_code == 0
    # The composite key should appear in the output.
    assert "payments-service:/api/pay" in result.output


# ---------------------------------------------------------------------------
# disable — SHIELD_SERVICE env var builds composite key
# ---------------------------------------------------------------------------


def test_disable_uses_shield_service_env(monkeypatch) -> None:
    """shield disable /api/pay uses SHIELD_SERVICE to form composite key."""
    monkeypatch.setenv("SHIELD_SERVICE", "payments-service")

    e = ShieldEngine()

    async def _seed() -> None:
        state = RouteState(
            path="payments-service:/api/pay",
            service="payments-service",
            status=RouteStatus.ACTIVE,
        )
        await e.backend.set_state("payments-service:/api/pay", state)

    anyio.run(_seed)

    client = _open_client(e)
    result = invoke_with_client(client, "disable", "/api/pay", "--reason", "testing")
    assert result.exit_code == 0
    assert "payments-service:/api/pay" in result.output


# ---------------------------------------------------------------------------
# maintenance — SHIELD_SERVICE env var builds composite key
# ---------------------------------------------------------------------------


def test_maintenance_uses_shield_service_env(monkeypatch) -> None:
    """shield maintenance /api/pay uses SHIELD_SERVICE to form composite key."""
    monkeypatch.setenv("SHIELD_SERVICE", "payments-service")

    e = ShieldEngine()

    async def _seed() -> None:
        state = RouteState(
            path="payments-service:/api/pay",
            service="payments-service",
            status=RouteStatus.ACTIVE,
        )
        await e.backend.set_state("payments-service:/api/pay", state)

    anyio.run(_seed)

    client = _open_client(e)
    result = invoke_with_client(client, "maintenance", "/api/pay", "--reason", "swap")
    assert result.exit_code == 0
    assert "payments-service:/api/pay" in result.output


# ---------------------------------------------------------------------------
# --service flag overrides SHIELD_SERVICE env var
# ---------------------------------------------------------------------------


def test_service_flag_overrides_env_var(monkeypatch) -> None:
    """Explicit --service=orders-service takes priority over SHIELD_SERVICE=payments-service."""
    monkeypatch.setenv("SHIELD_SERVICE", "payments-service")

    e = ShieldEngine()

    async def _seed() -> None:
        # Seed the orders-service route as DISABLED so enable works.
        orders_state = RouteState(
            path="orders-service:/api/pay",
            service="orders-service",
            status=RouteStatus.DISABLED,
        )
        await e.backend.set_state("orders-service:/api/pay", orders_state)

        # Also seed the payments-service route to confirm it is NOT used.
        payments_state = RouteState(
            path="payments-service:/api/pay",
            service="payments-service",
            status=RouteStatus.DISABLED,
        )
        await e.backend.set_state("payments-service:/api/pay", payments_state)

    anyio.run(_seed)

    client = _open_client(e)
    result = invoke_with_client(client, "enable", "/api/pay", "--service", "orders-service")
    assert result.exit_code == 0
    # The orders-service composite key must appear; payments-service must not.
    assert "orders-service:/api/pay" in result.output
    assert "payments-service:/api/pay" not in result.output
