"""Shared test helpers for the FastAPI test suite."""

from __future__ import annotations

import asyncio

from fastapi import FastAPI


async def _trigger_startup(app: FastAPI) -> None:
    """Fire all on_startup handlers registered on ``app.router``.

    ``starlette.Router.startup()`` was removed in Starlette 0.41+ in favour
    of the lifespan protocol.  This helper iterates the handlers directly so
    tests remain compatible across all supported Starlette versions.
    """
    for handler in app.router.on_startup:
        if asyncio.iscoroutinefunction(handler):
            await handler()
        else:
            handler()
