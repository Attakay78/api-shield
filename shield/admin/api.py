"""REST API route handlers for ShieldAdmin.

All handlers live under ``/api/`` within the mounted admin app and return
JSON responses.  The CLI uses these endpoints as its back-end.

Auth
----
Requests must carry a valid ``X-Shield-Token: <token>`` header.
When auth is not configured on the server every request is accepted and
the actor defaults to ``"anonymous"``.

Actor / Platform
----------------
Every mutating handler reads ``request.state.shield_actor`` and
``request.state.shield_platform`` (injected by the auth middleware) so
that audit log entries record who made the change and from which surface.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from datetime import UTC, datetime
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from shield.core.engine import ShieldEngine
from shield.core.exceptions import (
    AmbiguousRouteError,
    RouteNotFoundException,
    RouteProtectedException,
)
from shield.core.models import AuditEntry, MaintenanceWindow, RouteState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _engine(request: Request) -> ShieldEngine:
    """Return the ShieldEngine from app state."""
    return request.app.state.engine  # type: ignore[no-any-return]


def _actor(request: Request) -> str:
    """Return the authenticated actor name from request state."""
    return getattr(request.state, "shield_actor", "anonymous")


def _platform(request: Request) -> str:
    """Return the authenticated platform from request state."""
    return getattr(request.state, "shield_platform", "cli")


def _decode_path(encoded: str) -> str:
    """Decode a base64url-encoded route path key from a URL segment."""
    padding = 4 - len(encoded) % 4
    if padding != 4:
        encoded += "=" * padding
    return base64.urlsafe_b64decode(encoded).decode()


def _err(msg: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": msg}, status_code=status)


def _err_ambiguous(exc: AmbiguousRouteError) -> JSONResponse:
    return JSONResponse(
        {"error": str(exc), "ambiguous_matches": exc.matches},
        status_code=409,
    )


def _extract_token(request: Request) -> str | None:
    value = request.headers.get("X-Shield-Token", "").strip()
    return value or None


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------


async def auth_login(request: Request) -> JSONResponse:
    """POST /api/auth/login — exchange credentials for a token."""
    tm = request.app.state.token_manager
    auth_backend = request.app.state.auth_backend

    if auth_backend is None:
        return _err("Auth not configured on this server", 501)

    try:
        body = await request.json()
    except Exception:
        return _err("Invalid JSON body")

    username = body.get("username", "") if isinstance(body, dict) else ""
    password = body.get("password", "") if isinstance(body, dict) else ""
    platform = body.get("platform", "cli") if isinstance(body, dict) else "cli"
    if platform not in ("cli", "sdk"):
        platform = "cli"

    if not username or not password:
        return _err("username and password are required")

    if not auth_backend.authenticate_user(username, password):
        return _err("Invalid credentials", 401)

    token, expires_at = tm.create(username, platform=platform)
    return JSONResponse(
        {
            "token": token,
            "username": username,
            "expires_at": datetime.fromtimestamp(expires_at, UTC).isoformat(),
        }
    )


async def auth_logout(request: Request) -> JSONResponse:
    """POST /api/auth/logout — revoke the current bearer token."""
    token = _extract_token(request)
    if token:
        request.app.state.token_manager.revoke(token)
    return JSONResponse({"ok": True})


async def auth_me(request: Request) -> JSONResponse:
    """GET /api/auth/me — info about the authenticated user."""
    return JSONResponse({"username": _actor(request), "platform": _platform(request)})


# ---------------------------------------------------------------------------
# Route state endpoints
# ---------------------------------------------------------------------------


async def list_routes(request: Request) -> JSONResponse:
    """GET /api/routes — list all registered route states.

    Optional query param ``?service=<name>`` filters to a single service.
    """
    states = await _engine(request).list_states()
    service = request.query_params.get("service")
    if service:
        states = [s for s in states if s.service == service]
    return JSONResponse([s.model_dump(mode="json") for s in states])


async def get_route(request: Request) -> JSONResponse:
    """GET /api/routes/{path_key} — get state for one route."""
    path = _decode_path(request.path_params["path_key"])
    state = await _engine(request).get_state(path)
    return JSONResponse(state.model_dump(mode="json"))


async def enable_route(request: Request) -> JSONResponse:
    """POST /api/routes/{path_key}/enable — enable a route."""
    path = _decode_path(request.path_params["path_key"])
    actor = _actor(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    reason = body.get("reason", "") if isinstance(body, dict) else ""
    try:
        state = await _engine(request).enable(
            path, actor=actor, reason=reason, platform=_platform(request)
        )
    except RouteNotFoundException as exc:
        return _err(str(exc), 404)
    except AmbiguousRouteError as exc:
        return _err_ambiguous(exc)
    except RouteProtectedException as exc:
        return _err(str(exc), 409)
    return JSONResponse(state.model_dump(mode="json"))


async def disable_route(request: Request) -> JSONResponse:
    """POST /api/routes/{path_key}/disable — disable a route."""
    path = _decode_path(request.path_params["path_key"])
    actor = _actor(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    reason = body.get("reason", "") if isinstance(body, dict) else ""
    try:
        state = await _engine(request).disable(
            path, actor=actor, reason=reason, platform=_platform(request)
        )
    except RouteNotFoundException as exc:
        return _err(str(exc), 404)
    except AmbiguousRouteError as exc:
        return _err_ambiguous(exc)
    except RouteProtectedException as exc:
        return _err(str(exc), 409)
    return JSONResponse(state.model_dump(mode="json"))


async def maintenance_route(request: Request) -> JSONResponse:
    """POST /api/routes/{path_key}/maintenance — put a route in maintenance mode."""
    path = _decode_path(request.path_params["path_key"])
    actor = _actor(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    reason = body.get("reason", "") if isinstance(body, dict) else ""
    window = None
    if isinstance(body, dict):
        s, e = body.get("start"), body.get("end")
        if s and e:
            try:
                sd = datetime.fromisoformat(s)
                ed = datetime.fromisoformat(e)
                sd = sd if sd.tzinfo else sd.replace(tzinfo=UTC)
                ed = ed if ed.tzinfo else ed.replace(tzinfo=UTC)
                window = MaintenanceWindow(start=sd, end=ed, reason=reason)
            except ValueError:
                return _err("Invalid datetime for start/end")
    try:
        state = await _engine(request).set_maintenance(
            path, reason=reason, window=window, actor=actor, platform=_platform(request)
        )
    except RouteNotFoundException as exc:
        return _err(str(exc), 404)
    except AmbiguousRouteError as exc:
        return _err_ambiguous(exc)
    except RouteProtectedException as exc:
        return _err(str(exc), 409)
    return JSONResponse(state.model_dump(mode="json"))


async def env_route(request: Request) -> JSONResponse:
    """POST /api/routes/{path_key}/env — restrict route to specific environments."""
    path = _decode_path(request.path_params["path_key"])
    actor = _actor(request)
    try:
        body = await request.json()
    except Exception:
        return _err("Invalid JSON body")
    envs = body.get("envs", []) if isinstance(body, dict) else []
    if not isinstance(envs, list):
        return _err("envs must be a list of strings")
    try:
        state = await _engine(request).set_env_only(
            path, envs=envs, actor=actor, platform=_platform(request)
        )
    except RouteNotFoundException as exc:
        return _err(str(exc), 404)
    except AmbiguousRouteError as exc:
        return _err_ambiguous(exc)
    except RouteProtectedException as exc:
        return _err(str(exc), 409)
    return JSONResponse(state.model_dump(mode="json"))


async def schedule_route(request: Request) -> JSONResponse:
    """POST /api/routes/{path_key}/schedule — schedule a maintenance window."""
    path = _decode_path(request.path_params["path_key"])
    actor = _actor(request)
    try:
        body = await request.json()
    except Exception:
        return _err("Invalid JSON body")
    if not isinstance(body, dict):
        return _err("JSON body must be an object")
    s, e = body.get("start"), body.get("end")
    if not s or not e:
        return _err("start and end are required")
    reason = body.get("reason", "")
    try:
        sd = datetime.fromisoformat(s)
        ed = datetime.fromisoformat(e)
        sd = sd if sd.tzinfo else sd.replace(tzinfo=UTC)
        ed = ed if ed.tzinfo else ed.replace(tzinfo=UTC)
    except ValueError:
        return _err("Invalid datetime for start/end")
    window = MaintenanceWindow(start=sd, end=ed, reason=reason)
    try:
        await _engine(request).schedule_maintenance(
            path, window, actor=actor, platform=_platform(request)
        )
    except RouteNotFoundException as exc:
        return _err(str(exc), 404)
    except AmbiguousRouteError as exc:
        return _err_ambiguous(exc)
    except RouteProtectedException as exc:
        return _err(str(exc), 409)
    state = await _engine(request).get_state(path)
    return JSONResponse(state.model_dump(mode="json"))


async def cancel_schedule_route(request: Request) -> JSONResponse:
    """DELETE /api/routes/{path_key}/schedule — cancel a pending maintenance window."""
    path = _decode_path(request.path_params["path_key"])
    await _engine(request).scheduler.cancel(path)
    state = await _engine(request).get_state(path)
    return JSONResponse(state.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


async def list_audit(request: Request) -> JSONResponse:
    """GET /api/audit — return audit log entries (newest first).

    Optional query params:
    - ``?route=<path>`` — filter by exact route path
    - ``?service=<name>`` — filter to a single service (SDK mode)
    """
    route = request.query_params.get("route")
    service = request.query_params.get("service")
    try:
        limit = int(request.query_params.get("limit", "50"))
    except ValueError:
        limit = 50
    entries = await _engine(request).get_audit_log(path=route, limit=limit)
    if service:
        entries = [e for e in entries if e.service == service]
    return JSONResponse([e.model_dump(mode="json") for e in entries])


# ---------------------------------------------------------------------------
# Global maintenance
# ---------------------------------------------------------------------------


async def get_global(request: Request) -> JSONResponse:
    """GET /api/global — current global maintenance configuration."""
    cfg = await _engine(request).get_global_maintenance()
    return JSONResponse(cfg.model_dump(mode="json"))


async def global_enable_api(request: Request) -> JSONResponse:
    """POST /api/global/enable — enable global maintenance mode."""
    actor = _actor(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    reason = body.get("reason", "") if isinstance(body, dict) else ""
    exempt = body.get("exempt_paths", []) if isinstance(body, dict) else []
    include_fa = body.get("include_force_active", False) if isinstance(body, dict) else False
    await _engine(request).enable_global_maintenance(
        reason=reason,
        exempt_paths=exempt,
        include_force_active=include_fa,
        actor=actor,
        platform=_platform(request),
    )
    cfg = await _engine(request).get_global_maintenance()
    return JSONResponse(cfg.model_dump(mode="json"))


async def global_disable_api(request: Request) -> JSONResponse:
    """POST /api/global/disable — disable global maintenance mode."""
    actor = _actor(request)
    await _engine(request).disable_global_maintenance(actor=actor, platform=_platform(request))
    cfg = await _engine(request).get_global_maintenance()
    return JSONResponse(cfg.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# Rate limits
# ---------------------------------------------------------------------------


async def list_rate_limits(request: Request) -> JSONResponse:
    """GET /api/rate-limits — list all registered rate limit policies."""
    engine = _engine(request)
    policies = [p.model_dump(mode="json") for p in engine._rate_limit_policies.values()]
    return JSONResponse(policies)


async def get_rate_limit_hits(request: Request) -> JSONResponse:
    """GET /api/rate-limits/hits — return recent rate limit hits."""
    engine = _engine(request)
    route = request.query_params.get("route")
    try:
        limit = int(request.query_params.get("limit", "50"))
    except ValueError:
        limit = 50
    hits = await engine.get_rate_limit_hits(path=route, limit=limit)
    return JSONResponse([h.model_dump(mode="json") for h in hits])


async def reset_rate_limit(request: Request) -> JSONResponse:
    """DELETE /api/rate-limits/{path_key}/reset — reset counters for a route."""
    engine = _engine(request)
    path = _decode_path(request.path_params["path_key"])
    method = request.query_params.get("method")
    await engine.reset_rate_limit(path=path, method=method or None)
    return JSONResponse({"ok": True, "path": path})


async def set_rate_limit_policy_api(request: Request) -> JSONResponse:
    """POST /api/rate-limits — create or update a rate limit policy."""
    engine = _engine(request)
    actor = _actor(request)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    path = body.get("path")
    method = body.get("method", "GET")
    limit = body.get("limit")
    if not path or not limit:
        return JSONResponse({"error": "path and limit are required"}, status_code=400)

    try:
        policy = await engine.set_rate_limit_policy(
            path=path,
            method=method,
            limit=limit,
            algorithm=body.get("algorithm"),
            key_strategy=body.get("key_strategy"),
            burst=int(body.get("burst", 0)),
            actor=actor,
        )
    except RouteNotFoundException as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    return JSONResponse(policy.model_dump(mode="json"), status_code=201)


async def delete_rate_limit_policy_api(request: Request) -> JSONResponse:
    """DELETE /api/rate-limits/{path_key} — remove a rate limit policy.

    ``path_key`` is a base64url-encoded string in the form ``METHOD:path``
    (e.g. ``GET:/api/items``).  Use :func:`shield.cli.client._encode_path`
    to produce the correct encoding.
    """
    engine = _engine(request)
    actor = _actor(request)
    # base64url-decode the composite key ("METHOD:/path")
    raw_key = _decode_path(request.path_params["path_key"])
    if ":" not in raw_key:
        return JSONResponse({"error": "path_key must encode METHOD:path"}, status_code=400)
    method, path = raw_key.split(":", 1)
    await engine.delete_rate_limit_policy(path=path, method=method, actor=actor)
    return JSONResponse({"ok": True, "path": path, "method": method})


# ---------------------------------------------------------------------------
# Global rate limit
# ---------------------------------------------------------------------------


async def get_global_rate_limit(request: Request) -> JSONResponse:
    """GET /api/global-rate-limit — current global rate limit policy."""
    policy = await _engine(request).get_global_rate_limit()
    if policy is None:
        return JSONResponse({"enabled": False, "policy": None})
    return JSONResponse({"enabled": policy.enabled, "policy": policy.model_dump(mode="json")})


async def set_global_rate_limit_api(request: Request) -> JSONResponse:
    """POST /api/global-rate-limit — set or update the global rate limit policy."""
    engine = _engine(request)
    actor = _actor(request)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    limit = body.get("limit")
    if not limit:
        return JSONResponse({"error": "limit is required"}, status_code=400)

    exempt = body.get("exempt_routes", [])
    if not isinstance(exempt, list):
        return JSONResponse({"error": "exempt_routes must be a list"}, status_code=400)

    try:
        policy = await engine.set_global_rate_limit(
            limit=limit,
            algorithm=body.get("algorithm"),
            key_strategy=body.get("key_strategy"),
            on_missing_key=body.get("on_missing_key"),
            burst=int(body.get("burst", 0)),
            exempt_routes=exempt,
            actor=actor,
            platform=_platform(request),
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    return JSONResponse(policy.model_dump(mode="json"), status_code=201)


async def delete_global_rate_limit_api(request: Request) -> JSONResponse:
    """DELETE /api/global-rate-limit — remove the global rate limit policy."""
    engine = _engine(request)
    actor = _actor(request)
    await engine.delete_global_rate_limit(actor=actor, platform=_platform(request))
    return JSONResponse({"ok": True})


async def reset_global_rate_limit_api(request: Request) -> JSONResponse:
    """DELETE /api/global-rate-limit/reset — reset global rate limit counters."""
    engine = _engine(request)
    actor = _actor(request)
    await engine.reset_global_rate_limit(actor=actor, platform=_platform(request))
    return JSONResponse({"ok": True})


async def enable_global_rate_limit_api(request: Request) -> JSONResponse:
    """POST /api/global-rate-limit/enable — resume a paused global rate limit."""
    engine = _engine(request)
    actor = _actor(request)
    await engine.enable_global_rate_limit(actor=actor, platform=_platform(request))
    return JSONResponse({"ok": True})


async def disable_global_rate_limit_api(request: Request) -> JSONResponse:
    """POST /api/global-rate-limit/disable — pause the global rate limit."""
    engine = _engine(request)
    actor = _actor(request)
    await engine.disable_global_rate_limit(actor=actor, platform=_platform(request))
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# SDK endpoints — used by ShieldServerBackend / ShieldSDK clients
# ---------------------------------------------------------------------------


async def sdk_events(request: Request) -> StreamingResponse:
    """GET /api/sdk/events — SSE stream of typed route state and RL policy changes.

    SDK clients (``ShieldServerBackend``) connect here to keep their
    local cache current without polling.  Each event is a typed JSON
    envelope:

    * Route state change::

        data: {"type": "state", "payload": {...RouteState...}}

    * Rate limit policy change::

        data: {"type": "rl_policy", "action": "set", "key": "GET:/api/pay", "policy": {...}}
        data: {"type": "rl_policy", "action": "delete", "key": "GET:/api/pay"}

    When a backend does not support ``subscribe()`` (e.g. FileBackend)
    the endpoint falls back to 15-second keepalive pings so clients
    maintain their connection and rely on the full re-sync performed
    after each reconnect.
    """
    import json as _json

    engine = _engine(request)
    queue: asyncio.Queue[str] = asyncio.Queue()
    tasks: list[asyncio.Task[None]] = []

    async def _feed_states() -> None:
        try:
            async for state in engine.backend.subscribe():
                envelope = _json.dumps({"type": "state", "payload": state.model_dump(mode="json")})
                await queue.put(f"data: {envelope}\n\n")
        except NotImplementedError:
            pass
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("shield: SDK SSE state subscription error")

    async def _feed_rl_policies() -> None:
        try:
            async for event in engine.backend.subscribe_rate_limit_policy():
                envelope = _json.dumps({"type": "rl_policy", **event})
                await queue.put(f"data: {envelope}\n\n")
        except NotImplementedError:
            pass
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("shield: SDK SSE RL policy subscription error")

    async def _generate() -> object:
        tasks.append(asyncio.create_task(_feed_states()))
        tasks.append(asyncio.create_task(_feed_rl_policies()))
        try:
            while True:
                try:
                    # Block until an event arrives or 15 s elapses.
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield msg
                except TimeoutError:
                    # No event in 15 s — send a keepalive comment to hold the connection.
                    yield ": keepalive\n\n"
                except asyncio.CancelledError:
                    break
        finally:
            for t in tasks:
                t.cancel()

    return StreamingResponse(
        _generate(),  # type: ignore[arg-type]
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def sdk_register(request: Request) -> JSONResponse:
    """POST /api/sdk/register — batch-register routes from an SDK client.

    Applies server-wins semantics: routes that already exist in the
    backend are left untouched and their current state is returned.
    New routes are created with the initial state supplied by the SDK.

    The SDK sends states with ``path = "{app_id}:{original_path}"`` and
    ``service = app_id`` already set.  This endpoint trusts those values
    directly — no further rewriting is done here.

    Request body::

        {
            "app_id": "payments-service",
            "states": [ ...RouteState dicts with service-prefixed paths... ]
        }

    Response::

        {"states": [ ...current RouteState dicts... ]}
    """
    engine = _engine(request)
    try:
        body = await request.json()
    except Exception:
        return _err("Invalid JSON body")

    app_id = body.get("app_id", "unknown") if isinstance(body, dict) else "unknown"
    states_data = body.get("states", []) if isinstance(body, dict) else []
    if not isinstance(states_data, list):
        return _err("states must be a list")

    results: list[dict[str, Any]] = []
    for state_dict in states_data:
        try:
            incoming = RouteState.model_validate(state_dict)
        except Exception:
            continue

        # Ensure service field is always populated from app_id for legacy clients
        # that do not set it themselves.
        if not incoming.service:
            incoming = incoming.model_copy(update={"service": app_id})

        # Server-wins: if this namespaced key already exists, keep server state.
        try:
            existing = await engine.backend.get_state(incoming.path)
            results.append(existing.model_dump(mode="json"))
        except KeyError:
            await engine.backend.set_state(incoming.path, incoming)
            results.append(incoming.model_dump(mode="json"))

    logger.debug("shield: SDK registered %d route(s) from app_id=%s", len(results), app_id)
    return JSONResponse({"states": results})


async def list_services(request: Request) -> JSONResponse:
    """GET /api/services — return the distinct service names across all routes.

    Used by the dashboard dropdown and CLI to discover which services have
    registered routes with this Shield Server.  Routes without a service
    (embedded-mode routes) are not included.
    """
    states = await _engine(request).list_states()
    services = sorted({s.service for s in states if s.service})
    return JSONResponse(services)


async def sdk_audit(request: Request) -> JSONResponse:
    """POST /api/sdk/audit — receive an audit entry forwarded by an SDK client.

    SDK clients forward audit entries here so the Shield Server maintains
    a unified audit log across all connected services.
    """
    engine = _engine(request)
    try:
        body = await request.json()
    except Exception:
        return _err("Invalid JSON body")

    try:
        entry = AuditEntry.model_validate(body)
    except Exception as exc:
        return _err(f"Invalid audit entry: {exc}")

    await engine.backend.write_audit(entry)
    return JSONResponse({"ok": True})
