"""Tests for SwitchlyRouter."""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from switchly.core.backends.memory import MemoryBackend
from switchly.core.engine import SwitchlyEngine
from switchly.core.models import RouteStatus
from switchly.fastapi.decorators import disabled, env_only, maintenance
from switchly.fastapi.router import SwitchlyRouter
from tests.fastapi._helpers import _trigger_startup


@pytest.fixture
def engine() -> SwitchlyEngine:
    return SwitchlyEngine(backend=MemoryBackend(), current_env="production")


@pytest.fixture
def router(engine) -> SwitchlyRouter:
    return SwitchlyRouter(engine=engine)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


async def test_router_registers_maintenance_route(engine, router):
    @router.get("/payments")
    @maintenance(reason="DB migration")
    async def get_payments():
        return {"ok": True}

    await router.register_switchly_routes()

    # @router.get() → method-specific key "GET:/payments"
    state = await engine.backend.get_state("GET:/payments")
    assert state.status == RouteStatus.MAINTENANCE
    assert state.reason == "DB migration"


async def test_router_registers_env_gated_route(engine, router):
    @router.get("/debug")
    @env_only("dev")
    async def debug():
        return {"env": "dev"}

    await router.register_switchly_routes()

    state = await engine.backend.get_state("GET:/debug")
    assert state.status == RouteStatus.ENV_GATED
    assert state.allowed_envs == ["dev"]


async def test_router_registers_disabled_route(engine, router):
    @router.get("/old")
    @disabled(reason="gone")
    async def old():
        return {}

    await router.register_switchly_routes()

    state = await engine.backend.get_state("GET:/old")
    assert state.status == RouteStatus.DISABLED


async def test_router_registers_undecorated_routes_as_active(engine, router):
    @router.get("/health")
    async def health():
        return {"status": "ok"}

    await router.register_switchly_routes()

    # Undecorated routes are registered as ACTIVE so the CLI can
    # validate that a path actually exists in the application.
    state = await engine.backend.get_state("GET:/health")
    assert state.status.value == "active"


async def test_from_engine_factory(engine):
    router = SwitchlyRouter.from_engine(engine)
    assert router._switchly_engine is engine


# ---------------------------------------------------------------------------
# Startup hook fires automatically via app lifecycle
# ---------------------------------------------------------------------------


async def test_startup_registers_routes_via_app_lifespan(engine):
    """include_router forwards on_startup; triggering app startup registers routes."""
    router = SwitchlyRouter(engine=engine)

    @router.get("/pay")
    @maintenance(reason="test maint")
    async def pay():
        return {}

    app = FastAPI()
    app.include_router(router)

    # Trigger the app's startup events directly (equivalent to server startup).
    await _trigger_startup(app)

    state = await engine.backend.get_state("GET:/pay")
    assert state.status == RouteStatus.MAINTENANCE
