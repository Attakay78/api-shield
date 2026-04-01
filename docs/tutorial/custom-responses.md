# Custom Responses

By default, blocked routes return a structured JSON error body. You can replace this with any Starlette `Response`: HTML, plain text, a redirect, or a different JSON shape.

There are two places to configure this:

- **Per-route** via `response=` on the decorator
- **App-wide** via `responses=` on `WaygateMiddleware`

Resolution order per request: per-route `response=` → app-wide default → built-in JSON.

---

## Per-route

Every blocking decorator (`@maintenance`, `@disabled`, `@env_only`, `@rate_limit`) accepts a `response=` keyword. The value is a sync or async callable:

```python
(request: Request, exc: WaygateException) -> Response
```

### HTML page

```python
from starlette.requests import Request
from starlette.responses import HTMLResponse
from waygate.fastapi import maintenance

def maintenance_page(request: Request, exc) -> HTMLResponse:
    return HTMLResponse(
        f"<h1>Down for maintenance</h1><p>{exc.reason}</p>",
        status_code=503,
    )

@router.get("/payments")
@maintenance(reason="DB migration", response=maintenance_page)
async def payments():
    return {"payments": []}
```

### Redirect

```python
from starlette.responses import RedirectResponse
from waygate.fastapi import maintenance

@router.get("/payments")
@maintenance(
    reason="DB migration",
    response=lambda *_: RedirectResponse("/status"),
)
async def payments():
    return {"payments": []}
```

### Custom JSON shape

```python
from starlette.requests import Request
from starlette.responses import JSONResponse
from waygate.fastapi import maintenance

def branded_error(request: Request, exc) -> JSONResponse:
    return JSONResponse(
        {"ok": False, "message": str(exc), "support": "https://status.example.com"},
        status_code=503,
    )

@router.get("/payments")
@maintenance(reason="DB migration", response=branded_error)
async def payments():
    return {"payments": []}
```

### Async factory

Async factories work when you need to `await` something inside the response builder, such as rendering a template:

```python
from starlette.requests import Request
from starlette.responses import HTMLResponse
from waygate.fastapi import maintenance

async def maintenance_page(request: Request, exc) -> HTMLResponse:
    html = await render_template("maintenance.html", reason=exc.reason)
    return HTMLResponse(html, status_code=503)

@router.get("/payments")
@maintenance(reason="DB migration", response=maintenance_page)
async def payments():
    return {"payments": []}
```

---

## App-wide defaults

Set defaults once on `WaygateMiddleware`. Any route without a per-route `response=` falls back to these.

```python
from starlette.requests import Request
from starlette.responses import HTMLResponse
from waygate.fastapi import WaygateMiddleware

def maintenance_page(request: Request, exc) -> HTMLResponse:
    return HTMLResponse(
        f"<h1>Down for maintenance</h1><p>{exc.reason}</p>",
        status_code=503,
    )

app.add_middleware(
    WaygateMiddleware,
    engine=engine,
    responses={
        "maintenance": maintenance_page,
        "disabled":    lambda req, exc: HTMLResponse("<h1>Gone</h1>", status_code=503),
        "rate_limited": lambda req, exc: JSONResponse(
            {"error": "slow down", "retry_after": exc.retry_after_seconds},
            status_code=429,
        ),
        # omit "env_gated" to keep the default 403 JSON
    },
)
```

Available keys:

| Key | Triggered by | Default |
|---|---|---|
| `"maintenance"` | `MaintenanceException` | 503 JSON |
| `"disabled"` | `RouteDisabledException` | 503 JSON |
| `"env_gated"` | `EnvGatedException` | 403 JSON |
| `"rate_limited"` | `RateLimitExceededException` | 429 JSON |

---

## Exception attributes

The `exc` argument passed to your factory carries context for building the response:

| Exception | Useful attributes |
|---|---|
| `MaintenanceException` | `exc.reason`, `exc.retry_after`, `exc.path` |
| `RouteDisabledException` | `exc.reason`, `exc.path` |
| `EnvGatedException` | `exc.path`, `exc.current_env`, `exc.allowed_envs` |
| `RateLimitExceededException` | `exc.limit`, `exc.retry_after_seconds`, `exc.reset_at`, `exc.remaining`, `exc.key` |

---

## Next step

[**Tutorial: Admin Dashboard**](admin-dashboard.md)
