"""SwitchlySDK — connect a FastAPI app to a remote Switchly Server.

Drop-in alternative to the embedded setup.  State is managed centrally
from the Switchly Server dashboard or CLI; this SDK enforces it locally on
every request with zero network overhead.

Usage::

    from switchly.sdk import SwitchlySDK

    sdk = SwitchlySDK(
        server_url="http://switchly-server:9000",
        app_id="payments-service",
        token="...",    # omit if server has no auth
    )
    sdk.attach(app)

    @app.get("/payments")
    @maintenance(reason="DB migration")   # optional — manage from dashboard instead
    async def payments():
        return {"ok": True}

The CLI then points at the Switchly Server, not at this service::

    switchly config set-url http://switchly-server:9000
    switchly status                         # routes from ALL connected services
    switchly disable payments-service /api/payments --reason "migration"
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from switchly.core.backends.base import SwitchlyBackend
from switchly.core.backends.server import SwitchlyServerBackend
from switchly.core.engine import SwitchlyEngine

if TYPE_CHECKING:
    from fastapi import FastAPI

__all__ = ["SwitchlySDK"]

logger = logging.getLogger(__name__)


class SwitchlySDK:
    """Connect a FastAPI application to a remote Switchly Server.

    Parameters
    ----------
    server_url:
        Base URL of the Switchly Server (e.g. ``http://switchly-server:9000``).
        If the Switchly Server is mounted under a prefix (e.g. ``/switchly``),
        include the prefix: ``http://myapp.com/switchly``.
    app_id:
        Unique name for this service shown in the Switchly Server dashboard.
        Use a stable identifier like ``"payments-service"`` or
        ``"orders-api"``.
    token:
        Pre-issued bearer token for Switchly Server auth.  Takes priority
        over ``username``/``password`` if both are provided.  Omit if
        the server has no auth configured.
    username:
        Switchly Server username.  When provided alongside ``password``
        (and no ``token``), the SDK automatically calls
        ``POST /api/auth/login`` on startup with ``platform="sdk"`` and
        obtains a long-lived service token — no manual token management
        required.  Store credentials in environment variables and inject
        them at deploy time::

            sdk = SwitchlySDK(
                server_url=os.environ["SWITCHLY_SERVER_URL"],
                app_id="payments-service",
                username=os.environ["SWITCHLY_USERNAME"],
                password=os.environ["SWITCHLY_PASSWORD"],
            )
    password:
        Switchly Server password.  Used together with ``username``.
    reconnect_delay:
        Seconds between SSE reconnect attempts after a dropped connection.
        Defaults to 5 seconds.
    rate_limit_backend:
        Optional shared backend for rate limit counter storage.  When
        ``None`` (default) each instance maintains its own in-process
        counters — a ``100/minute`` limit is enforced independently on
        each replica.  Pass a :class:`~switchly.core.backends.redis.RedisBackend`
        pointing at a shared Redis instance to enforce the limit
        **across all replicas combined**::

            from switchly.core.backends.redis import RedisBackend

            sdk = SwitchlySDK(
                server_url="http://switchly:9000",
                app_id="payments-service",
                rate_limit_backend=RedisBackend(url="redis://redis:6379/1"),
            )
    """

    def __init__(
        self,
        server_url: str,
        app_id: str,
        token: str | None = None,
        username: str | None = None,
        password: str | None = None,
        reconnect_delay: float = 5.0,
        rate_limit_backend: SwitchlyBackend | None = None,
    ) -> None:
        self._backend = SwitchlyServerBackend(
            server_url=server_url,
            app_id=app_id,
            token=token,
            username=username,
            password=password,
            reconnect_delay=reconnect_delay,
        )
        self._engine = SwitchlyEngine(
            backend=self._backend,
            rate_limit_backend=rate_limit_backend,
        )

    @property
    def engine(self) -> SwitchlyEngine:
        """The underlying :class:`~switchly.core.engine.SwitchlyEngine`.

        Use this if you need direct engine access (e.g. to call
        ``engine.disable()`` programmatically from within the service).
        """
        return self._engine

    def use_openfeature(
        self,
        hooks: list[Any] | None = None,
        domain: str = "switchly",
    ) -> None:
        """Enable OpenFeature feature-flag evaluation for this SDK client.

        Must be called **before** :meth:`attach`.

        Activates :class:`~switchly.sdk.flag_provider.SwitchlySDKFlagProvider`
        which:

        * On startup fetches all flags/segments from the Switchly Server via
          ``GET /api/flags`` and ``GET /api/segments``.
        * Stays current by listening to ``flag_updated``, ``flag_deleted``,
          ``segment_updated``, and ``segment_deleted`` events on the
          existing SSE connection — no extra network connections needed.

        Usage::

            sdk = SwitchlySDK(server_url="http://switchly:9000", app_id="my-svc")
            sdk.use_openfeature()
            sdk.attach(app)

            # Evaluate anywhere via the engine's flag client:
            value = await sdk.engine.flag_client.get_boolean_value(
                "my-flag", default_value=False
            )

        Parameters
        ----------
        hooks:
            Optional list of OpenFeature :class:`Hook` objects to register
            globally for this provider.
        domain:
            OpenFeature provider domain name (default ``"switchly"``).
        """
        from switchly.sdk.flag_provider import SwitchlySDKFlagProvider

        provider = SwitchlySDKFlagProvider(self._backend)
        self._engine.use_openfeature(provider=provider, hooks=hooks, domain=domain)

    def attach(self, app: FastAPI) -> None:
        """Wire switchly middleware and lifecycle hooks into *app*.

        Call this once after creating the FastAPI app and before
        defining routes::

            sdk.attach(app)

            @app.get("/payments")
            async def payments():
                ...

        What ``attach`` does:

        1. Adds :class:`~switchly.fastapi.middleware.SwitchlyMiddleware` so
           every request is checked against the local state cache.
        2. On startup: syncs state from the Switchly Server, starts the SSE
           listener, discovers decorated routes, and registers any new
           ones with the server.
        3. On shutdown: closes the SSE connection and HTTP client cleanly.

        Parameters
        ----------
        app:
            The :class:`fastapi.FastAPI` application to attach to.
        """
        from fastapi.routing import APIRoute

        from switchly.fastapi.middleware import SwitchlyMiddleware

        app.add_middleware(SwitchlyMiddleware, engine=self._engine)

        @app.on_event("startup")
        async def _switchly_sdk_startup() -> None:
            # Start engine background tasks (pub/sub listeners, etc.)
            await self._engine.start()
            # Connect to Switchly Server: sync state + open SSE stream.
            await self._backend.startup()

            # Discover routes decorated with @maintenance, @disabled, etc.
            # and register any that are new to the Switchly Server.
            # Use the same method-prefixed key format as SwitchlyRouter
            # (e.g. "GET:/api/payments") so that routes registered by
            # SwitchlyRouter before the SDK startup don't create duplicates
            # with missing-method variants.
            switchly_routes: list[tuple[str, dict[str, Any]]] = []
            for route in app.routes:
                if not isinstance(route, APIRoute):
                    continue
                if not hasattr(route.endpoint, "__switchly_meta__"):
                    continue
                meta: dict[str, Any] = route.endpoint.__switchly_meta__
                methods: set[str] = route.methods or set()
                if methods:
                    for method in sorted(methods):
                        switchly_routes.append((f"{method}:{route.path}", meta))
                else:
                    switchly_routes.append((route.path, meta))

            if switchly_routes:
                # register_batch() is persistence-first: routes already present
                # in the cache (synced from server) are skipped.  All set_state()
                # calls queue to _pending while _startup_done is False; they are
                # flushed in a single HTTP round-trip by _flush_pending() below.
                await self._engine.register_batch(switchly_routes)

            # Push any truly new routes (not already on the server) in one HTTP
            # round-trip, then mark startup complete so that subsequent
            # set_state() calls (runtime mutations) push immediately.
            await self._backend._flush_pending()

            logger.info(
                "SwitchlySDK[%s]: attached — %d switchly route(s) discovered",
                self._backend._app_id,
                len(switchly_routes),
            )

        @app.on_event("shutdown")
        async def _switchly_sdk_shutdown() -> None:
            await self._backend.shutdown()
            await self._engine.stop()
