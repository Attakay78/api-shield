"""Rate limiting core for switchly.

Optional feature — requires ``pip install switchly[rate-limit]``.

Modules
-------
models   — Pydantic models: RateLimitPolicy, RateLimitResult, etc.
storage  — Storage bridge wrapping the ``limits`` library backends.
keys     — Key extraction from requests (IP, user, API key, custom).
limiter  — SwitchlyRateLimiter orchestrating checks against policies.
"""
