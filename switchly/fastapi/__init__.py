"""FastAPI adapter for switchly.

Exports the middleware, router, OpenAPI helper, and all decorators so that
users need only a single import line::

    from switchly.fastapi import (
        SwitchlyMiddleware,
        SwitchlyRouter,
        apply_switchly_to_openapi,
        maintenance,
        env_only,
        disabled,
        force_active,
    )
"""

from switchly.admin.app import SwitchlyAdmin
from switchly.admin.auth import SwitchlyAuthBackend, make_auth_backend
from switchly.fastapi.decorators import (
    ResponseFactory,
    deprecated,
    disabled,
    env_only,
    force_active,
    maintenance,
    rate_limit,
)
from switchly.fastapi.dependencies import SwitchlyGuard, configure_switchly
from switchly.fastapi.middleware import SwitchlyMiddleware
from switchly.fastapi.openapi import apply_switchly_to_openapi, setup_switchly_docs
from switchly.fastapi.router import SwitchlyRouter, scan_routes

__all__ = [
    "SwitchlyAdmin",
    "SwitchlyAuthBackend",
    "make_auth_backend",
    "SwitchlyMiddleware",
    "SwitchlyRouter",
    "SwitchlyGuard",
    "configure_switchly",
    "scan_routes",
    "apply_switchly_to_openapi",
    "setup_switchly_docs",
    "ResponseFactory",
    "maintenance",
    "env_only",
    "disabled",
    "deprecated",
    "force_active",
    "rate_limit",
]
