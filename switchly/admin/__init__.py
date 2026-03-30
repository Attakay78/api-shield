"""Switchly Admin — unified admin interface for switchly.

Exposes both the HTMX dashboard UI *and* a REST API that the ``switchly`` CLI
uses as its HTTP back-end.  Mount a single :func:`SwitchlyAdmin` instance on
your FastAPI / Starlette application and both interfaces are available
immediately.
"""

from switchly.admin.app import SwitchlyAdmin

__all__ = ["SwitchlyAdmin"]
