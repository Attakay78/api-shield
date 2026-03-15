"""Shield Admin — unified admin interface for api-shield.

Exposes both the HTMX dashboard UI *and* a REST API that the ``shield`` CLI
uses as its HTTP back-end.  Mount a single :func:`ShieldAdmin` instance on
your FastAPI / Starlette application and both interfaces are available
immediately.
"""

from shield.admin.app import ShieldAdmin

__all__ = ["ShieldAdmin"]
