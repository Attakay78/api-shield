"""ShieldServer — standalone Shield Server factory.

Deploy this once as its own service.  All your FastAPI applications
connect to it via :class:`~shield.sdk.ShieldSDK`.

Usage::

    # shield_server.py
    from shield.server import ShieldServer
    from shield.core.backends.redis import RedisBackend

    app = ShieldServer(
        backend=RedisBackend("redis://localhost:6379"),
        auth=("admin", "secret"),
    )

    # Run with: uvicorn shield_server:app

Then in each service::

    from shield.sdk import ShieldSDK

    sdk = ShieldSDK(
        server_url="http://shield-server:9000",
        app_id="payments-service",
        token="...",
    )
    sdk.attach(app)

And point the CLI at the server::

    shield config set-url http://shield-server:9000
    shield login admin
    shield status

Use ``RedisBackend`` so every connected service receives live state
updates via the SSE channel.  ``MemoryBackend`` works for local
development with a single service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.types import ASGIApp

    from shield.admin.auth import AuthConfig
    from shield.core.backends.base import ShieldBackend

__all__ = ["ShieldServer"]


def ShieldServer(
    backend: ShieldBackend,
    auth: AuthConfig = None,
    token_expiry: int = 86400,
    sdk_token_expiry: int = 31536000,
    secret_key: str | None = None,
    prefix: str = "",
) -> ASGIApp:
    """Create a standalone Shield Server ASGI application.

    The returned app exposes the full :class:`~shield.admin.app.ShieldAdmin`
    surface: dashboard UI, REST API, and the SDK SSE/register endpoints.

    Parameters
    ----------
    backend:
        Storage backend.  Use :class:`~shield.core.backends.redis.RedisBackend`
        for multi-service deployments — Redis pub/sub ensures every SDK
        client receives live updates when state changes.
        :class:`~shield.core.backends.memory.MemoryBackend` is fine for
        local development with a single service.
    auth:
        Credentials config — same as :func:`~shield.admin.app.ShieldAdmin`:

        * ``None`` — open access (no credentials required)
        * ``("user", "pass")`` — single user
        * ``[("u1", "p1"), ("u2", "p2")]`` — multiple users
        * :class:`~shield.admin.auth.ShieldAuthBackend` instance — custom
    token_expiry:
        Token lifetime in seconds for dashboard and CLI users.
        Default: 86400 (24 h).
    sdk_token_expiry:
        Token lifetime in seconds for SDK service tokens.
        Default: 31536000 (1 year).  Service apps that authenticate with
        ``username``/``password`` via :class:`~shield.sdk.ShieldSDK`
        receive a token of this duration so they never need manual
        re-authentication.
    secret_key:
        HMAC signing key.  Use a stable value so tokens survive process
        restarts.  Defaults to a random key (tokens invalidated on restart).
    prefix:
        URL prefix if the server app is mounted under a sub-path.
        Usually empty when running as a standalone service.

    Returns
    -------
    ASGIApp
        A Starlette ASGI application ready to be served by uvicorn /
        gunicorn, or mounted on another app.
    """
    from shield.admin.app import ShieldAdmin
    from shield.core.engine import ShieldEngine

    engine = ShieldEngine(backend=backend)
    return ShieldAdmin(
        engine=engine,
        auth=auth,
        token_expiry=token_expiry,
        sdk_token_expiry=sdk_token_expiry,
        secret_key=secret_key,
        prefix=prefix,
    )
