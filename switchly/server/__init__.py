"""SwitchlyServer — standalone Switchly Server factory.

Deploy this once as its own service.  All your FastAPI applications
connect to it via :class:`~switchly.sdk.SwitchlySDK`.

Usage::

    # switchly_server.py
    from switchly.server import SwitchlyServer
    from switchly.core.backends.redis import RedisBackend

    app = SwitchlyServer(
        backend=RedisBackend("redis://localhost:6379"),
        auth=("admin", "secret"),
    )

    # Run with: uvicorn switchly_server:app

Then in each service::

    from switchly.sdk import SwitchlySDK

    sdk = SwitchlySDK(
        server_url="http://switchly-server:9000",
        app_id="payments-service",
        token="...",
    )
    sdk.attach(app)

And point the CLI at the server::

    switchly config set-url http://switchly-server:9000
    switchly login admin
    switchly status

Use ``RedisBackend`` so every connected service receives live state
updates via the SSE channel.  ``MemoryBackend`` works for local
development with a single service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.types import ASGIApp

    from switchly.admin.auth import AuthConfig
    from switchly.core.backends.base import SwitchlyBackend

__all__ = ["SwitchlyServer"]


def SwitchlyServer(
    backend: SwitchlyBackend,
    auth: AuthConfig = None,
    token_expiry: int = 86400,
    sdk_token_expiry: int = 31536000,
    secret_key: str | None = None,
    prefix: str = "",
) -> ASGIApp:
    """Create a standalone Switchly Server ASGI application.

    The returned app exposes the full :class:`~switchly.admin.app.SwitchlyAdmin`
    surface: dashboard UI, REST API, and the SDK SSE/register endpoints.

    Parameters
    ----------
    backend:
        Storage backend.  Use :class:`~switchly.core.backends.redis.RedisBackend`
        for multi-service deployments — Redis pub/sub ensures every SDK
        client receives live updates when state changes.
        :class:`~switchly.core.backends.memory.MemoryBackend` is fine for
        local development with a single service.
    auth:
        Credentials config — same as :func:`~switchly.admin.app.SwitchlyAdmin`:

        * ``None`` — open access (no credentials required)
        * ``("user", "pass")`` — single user
        * ``[("u1", "p1"), ("u2", "p2")]`` — multiple users
        * :class:`~switchly.admin.auth.SwitchlyAuthBackend` instance — custom
    token_expiry:
        Token lifetime in seconds for dashboard and CLI users.
        Default: 86400 (24 h).
    sdk_token_expiry:
        Token lifetime in seconds for SDK service tokens.
        Default: 31536000 (1 year).  Service apps that authenticate with
        ``username``/``password`` via :class:`~switchly.sdk.SwitchlySDK`
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
    from switchly.admin.app import SwitchlyAdmin
    from switchly.core.engine import SwitchlyEngine

    engine = SwitchlyEngine(backend=backend)
    return SwitchlyAdmin(
        engine=engine,
        auth=auth,
        token_expiry=token_expiry,
        sdk_token_expiry=sdk_token_expiry,
        secret_key=secret_key,
        prefix=prefix,
    )
