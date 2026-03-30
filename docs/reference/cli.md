# CLI Reference

The `switchly` CLI lets you manage routes, view the audit log, and control global maintenance from the terminal. It communicates with a running `SwitchlyAdmin` instance over HTTP — it does not access the backend directly.

```bash
uv add "switchly[cli]"
```

!!! tip "Set the server URL first"
    Before using any commands, point the CLI at your running server:

    ```bash
    switchly config set-url http://localhost:8000/switchly
    switchly login admin
    ```

    See [Server URL discovery](#server-url-discovery) for other ways to configure the URL.

---

## Auth commands

### `switchly login`

Authenticate with a `SwitchlyAdmin` server and store the token locally. The CLI will prompt for a password if `--password` is omitted.

```bash
switchly login <username>
```

```bash
switchly login admin                     # prompts for password interactively
switchly login admin --password secret   # inline, useful in CI pipelines
```

| Option | Description |
|---|---|
| `--password TEXT` | Password for the given username. Omit to be prompted securely. |

Tokens are saved to `~/.switchly/config.json` with an expiry timestamp. The CLI automatically uses the stored token for all subsequent commands until it expires or you log out.

---

### `switchly logout`

Revoke the server-side token and clear local credentials.

```bash
switchly logout
```

---

## Multi-service commands

### `switchly services`

List all distinct service names registered with the Switchly Server. Use this to discover which services are currently connected before switching context with `SWITCHLY_SERVICE`.

```bash
switchly services
```

---

### `switchly current-service`

Show the active service context (the value of the `SWITCHLY_SERVICE` environment variable). Useful for confirming which service subsequent commands will target.

```bash
switchly current-service
```

**When `SWITCHLY_SERVICE` is set:**

```
Active service: payments-service  (from SWITCHLY_SERVICE)
```

**When `SWITCHLY_SERVICE` is not set:**

```
No active service set.
Set one with: export SWITCHLY_SERVICE=<service-name>
```

---

## Route commands

Route commands accept an optional `--service` flag to scope to a specific service. All five commands also read the `SWITCHLY_SERVICE` environment variable as a fallback — an explicit `--service` flag always wins.

```bash
export SWITCHLY_SERVICE=payments-service   # set once
switchly status                            # scoped to payments-service
switchly enable GET:/payments              # scoped to payments-service
unset SWITCHLY_SERVICE
switchly status --service orders-service   # explicit flag, no env var needed
```

### `switchly status`

Show all registered routes and their current state, or inspect a single route in detail.

```bash
switchly status                          # all routes, page 1
switchly status GET:/payments            # one route
switchly status --page 2                 # next page
switchly status --per-page 50           # 50 rows per page
switchly status --service payments-service  # scope to one service
```

| Option | Description |
|---|---|
| `--page INT` | Page number to display when listing all routes (default: 1) |
| `--per-page INT` | Rows per page (default: 20) |
| `--service TEXT` | Filter to a specific service. Falls back to `SWITCHLY_SERVICE` env var. |

**Example output:**

```
┌─────────────────────┬─────────────┬──────────────────────┬──────────────┐
│ Route               │ Status      │ Reason               │ Since        │
├─────────────────────┼─────────────┼──────────────────────┼──────────────┤
│ GET /payments       │ MAINTENANCE │ DB migration         │ 2 hours ago  │
│ GET /debug          │ ENV_GATED   │ dev, staging only    │ startup      │
│ GET /health         │ ACTIVE      │                      │              │
└─────────────────────┴─────────────┴──────────────────────┴──────────────┘
  Showing 1-3  (last page)
```

---

### `switchly enable`

Restore a route to `ACTIVE`. Works regardless of the current status.

```bash
switchly enable GET:/payments
switchly enable GET:/payments --service payments-service
```

| Option | Description |
|---|---|
| `--service TEXT` | Target service. Falls back to `SWITCHLY_SERVICE` env var. |

---

### `switchly disable`

Permanently disable a route. Returns 503 to all callers.

```bash
switchly disable GET:/payments
switchly disable GET:/payments --reason "Use /v2/payments instead"
switchly disable GET:/payments --reason "hotfix" --until 2h
switchly disable GET:/payments --service payments-service --reason "hotfix"
```

| Option | Description |
|---|---|
| `--reason TEXT` | Reason shown in error responses and recorded in the audit log |
| `--until DURATION` | Automatically re-enable after this duration. Accepts `2h`, `30m`, `1d`, or an ISO 8601 datetime. |
| `--service TEXT` | Target service. Falls back to `SWITCHLY_SERVICE` env var. |

---

### `switchly maintenance`

Put a route in maintenance mode. Optionally schedule automatic activation and deactivation.

```bash
switchly maintenance GET:/payments --reason "DB swap"
switchly maintenance GET:/payments --service payments-service --reason "DB swap"
```

```bash
# Scheduled window
switchly maintenance GET:/payments \
  --reason "Planned migration" \
  --start 2025-06-01T02:00Z \
  --end   2025-06-01T04:00Z
```

| Option | Description |
|---|---|
| `--reason TEXT` | Shown in the 503 error response |
| `--start DATETIME` | Start of the maintenance window (ISO 8601). Maintenance activates automatically at this time. |
| `--end DATETIME` | End of the maintenance window. Sets the `Retry-After` header and restores `ACTIVE` automatically. |
| `--service TEXT` | Target service. Falls back to `SWITCHLY_SERVICE` env var. |

---

### `switchly schedule`

Schedule a future maintenance window without activating maintenance now. The route stays `ACTIVE` until `--start` is reached.

```bash
switchly schedule GET:/payments \
  --start 2025-06-01T02:00Z \
  --end   2025-06-01T04:00Z \
  --reason "Planned migration"
switchly schedule GET:/payments --service payments-service \
  --start 2025-06-01T02:00Z --end 2025-06-01T04:00Z
```

| Option | Description |
|---|---|
| `--start DATETIME` | When to activate maintenance (ISO 8601, required) |
| `--end DATETIME` | When to restore the route to `ACTIVE` (ISO 8601, required) |
| `--reason TEXT` | Reason shown in the 503 response during the window |
| `--service TEXT` | Target service. Falls back to `SWITCHLY_SERVICE` env var. |

---

## Global maintenance commands

Global maintenance blocks every non-exempt route at once, without requiring individual route changes.

### `switchly global status`

Show the current global maintenance state, including whether it is active, the reason, and any exempt paths.

```bash
switchly global status
```

---

### `switchly global enable`

Block all non-exempt routes immediately.

```bash
switchly global enable --reason "Deploying v2"
switchly global enable --reason "Deploying v2" --exempt /health --exempt GET:/status
switchly global enable --reason "Hard lockdown" --include-force-active
```

| Option | Description |
|---|---|
| `--reason TEXT` | Shown in every 503 response while global maintenance is active |
| `--exempt PATH` | Exempt a path from the global block (repeatable). Use bare `/health` for any method, or `GET:/health` for a specific method. |
| `--include-force-active` | Block `@force_active` routes too. Use with care — this will block health checks and readiness probes. |

!!! warning "Exempting health checks"
    Always exempt your health and readiness probe endpoints before enabling global maintenance, unless you intend to take the instance out of rotation:

    ```bash
    switchly global enable --reason "Deploying v2" --exempt /health --exempt /ready
    ```

---

### `switchly global disable`

Restore all routes to their individual states. Each route resumes the status it had before global maintenance was enabled.

```bash
switchly global disable
```

---

### `switchly global exempt-add`

Add a path to the exemption list while global maintenance is already active, without toggling the mode.

```bash
switchly global exempt-add /monitoring/ping
```

---

### `switchly global exempt-remove`

Remove a path from the exemption list.

```bash
switchly global exempt-remove /monitoring/ping
```

---

## `switchly sm` / `switchly service-maintenance`

`switchly sm` and `switchly service-maintenance` are aliases for the same command group. Puts all routes of one service into maintenance mode without affecting other services. The affected SDK client's `app_id` must match the service name.

```bash
switchly sm enable payments-service --reason "DB migration"
switchly service-maintenance enable payments-service   # identical
```

### `switchly sm status`

Show the current maintenance configuration for a service.

```bash
switchly sm status <service>
```

```bash
switchly sm status payments-service
```

**Example output:**

```
  Service maintenance (payments-service): ON
  Reason               : DB migration
  Include @force_active: no
  Exempt paths         :
    • /health
```

---

### `switchly sm enable`

Block all routes of a service immediately. Routes return `503` until `switchly sm disable` is called.

```bash
switchly sm enable <service>
```

```bash
switchly sm enable payments-service --reason "DB migration"
switchly sm enable payments-service --reason "Upgrade" --exempt /health --exempt GET:/ready
switchly sm enable orders-service --include-force-active
```

| Option | Description |
|---|---|
| `--reason TEXT` | Shown in every 503 response while maintenance is active |
| `--exempt PATH` | Exempt a path from the block (repeatable). Use bare `/health` or `GET:/health`. |
| `--include-force-active` | Also block `@force_active` routes. Use with care. |

---

### `switchly sm disable`

Restore all routes of a service to their individual states.

```bash
switchly sm disable <service>
```

```bash
switchly sm disable payments-service
```

---

## Rate limit commands

`switchly rl` and `switchly rate-limits` are aliases for the same command group — use whichever you prefer. Requires `switchly[rate-limit]` on the server.

```bash
switchly rl list          # short form
switchly rate-limits list # identical
```

### `switchly rl list`

Show all registered rate limit policies.

```bash
switchly rl list
switchly rl list --page 2
switchly rl list --per-page 50
```

| Option | Description |
|---|---|
| `--page INT` | Page number to display (default: 1) |
| `--per-page INT` | Rows per page (default: 20) |

---

### `switchly rl set`

Register or update a rate limit policy at runtime. Changes take effect on the next request.

```bash
switchly rl set <route> <limit>
```

```bash
switchly rl set GET:/public/posts 20/minute
switchly rl set GET:/public/posts 5/second --algorithm fixed_window
switchly rl set GET:/search 10/minute --key global
```

| Option | Description |
|---|---|
| `--algorithm TEXT` | Counting algorithm: `fixed_window`, `sliding_window`, `moving_window`, `token_bucket` |
| `--key TEXT` | Key strategy: `ip`, `user`, `api_key`, `global` |

---

### `switchly rl reset`

Clear all counters for a route immediately. Clients get their full quota back on the next request.

```bash
switchly rl reset GET:/public/posts
```

---

### `switchly rl delete`

Remove a persisted policy override from the backend.

```bash
switchly rl delete GET:/public/posts
```

---

### `switchly rl hits`

Show the blocked requests log, newest first. The `Path` column combines the HTTP method and route path.

```bash
switchly rl hits                    # page 1, 20 rows
switchly rl hits --page 2           # next page
switchly rl hits --per-page 50     # 50 rows per page
switchly rl hits --route /api/pay   # filter to one route
```

| Option | Description |
|---|---|
| `--route TEXT` | Filter entries to a single route path |
| `--page INT` | Page number to display (default: 1) |
| `--per-page INT` | Rows per page (default: 20) |

---

## Global rate limit commands

`switchly grl` and `switchly global-rate-limit` are aliases for the same command group. Requires `switchly[rate-limit]` on the server.

```bash
switchly grl get
switchly global-rate-limit get   # identical
```

### `switchly grl get`

Show the current global rate limit policy, including limit, algorithm, key strategy, burst, exempt routes, and enabled state.

```bash
switchly grl get
```

---

### `switchly grl set`

Configure the global rate limit. Creates a new policy or replaces the existing one.

```bash
switchly grl set <limit>
```

```bash
switchly grl set 1000/minute
switchly grl set 500/minute --algorithm sliding_window --key ip
switchly grl set 2000/hour --burst 50 --exempt /health --exempt GET:/metrics
```

| Option | Description |
|---|---|
| `--algorithm TEXT` | Counting algorithm: `fixed_window`, `sliding_window`, `moving_window`, `token_bucket` |
| `--key TEXT` | Key strategy: `ip`, `user`, `api_key`, `global` |
| `--burst INT` | Extra requests above the base limit |
| `--exempt TEXT` | Exempt route (repeatable). Bare path (`/health`) or method-prefixed (`GET:/metrics`) |

---

### `switchly grl delete`

Remove the global rate limit policy entirely.

```bash
switchly grl delete
```

---

### `switchly grl reset`

Clear all global rate limit counters. The policy is kept; clients get their full quota back on the next request.

```bash
switchly grl reset
```

---

### `switchly grl enable`

Resume a paused global rate limit policy.

```bash
switchly grl enable
```

---

### `switchly grl disable`

Pause the global rate limit without removing it. Per-route policies continue to enforce normally.

```bash
switchly grl disable
```

---

## `switchly srl` / `switchly service-rate-limit`

`switchly srl` and `switchly service-rate-limit` are aliases for the same command group. Manages the rate limit policy for a single service — applies to all routes of that service. Requires `switchly[rate-limit]` on the server.

```bash
switchly srl get payments-service
switchly service-rate-limit get payments-service   # identical
```

### `switchly srl get`

Show the current rate limit policy for a service, including limit, algorithm, key strategy, burst, exempt routes, and enabled state.

```bash
switchly srl get <service>
```

```bash
switchly srl get payments-service
```

---

### `switchly srl set`

Configure the rate limit for a service. Creates a new policy or replaces the existing one.

```bash
switchly srl set <service> <limit>
```

```bash
switchly srl set payments-service 1000/minute
switchly srl set payments-service 500/minute --algorithm sliding_window --key ip
switchly srl set payments-service 2000/hour --burst 50 --exempt /health --exempt GET:/metrics
```

| Option | Description |
|---|---|
| `--algorithm TEXT` | Counting algorithm: `fixed_window`, `sliding_window`, `moving_window`, `token_bucket` |
| `--key TEXT` | Key strategy: `ip`, `user`, `api_key`, `global` |
| `--burst INT` | Extra requests above the base limit |
| `--exempt TEXT` | Exempt route (repeatable). Bare path (`/health`) or method-prefixed (`GET:/metrics`) |

---

### `switchly srl delete`

Remove the service rate limit policy entirely.

```bash
switchly srl delete <service>
```

```bash
switchly srl delete payments-service
```

---

### `switchly srl reset`

Clear all counters for the service. The policy is kept; clients get their full quota back on the next request.

```bash
switchly srl reset <service>
```

```bash
switchly srl reset payments-service
```

---

### `switchly srl enable`

Resume a paused service rate limit policy.

```bash
switchly srl enable <service>
```

---

### `switchly srl disable`

Pause the service rate limit without removing it. Per-route policies continue to enforce normally.

```bash
switchly srl disable <service>
```

---

## Audit log

### `switchly log`

Display the audit log, newest entries first. The `Status` column shows `old > new` for route state changes and a coloured action label for rate limit policy changes (including global RL actions such as `global set`, `global reset`, `global enabled`, `global disabled`, and service RL actions such as `svc set`, `svc reset`, `svc enabled`, `svc disabled`). The `Path` column shows human-readable labels for sentinel-keyed entries: `[Global Maintenance]`, `[Global Rate Limit]`, `[{service} Maintenance]`, and `[{service} Rate Limit]`.

```bash
switchly log                          # page 1, 20 rows
switchly log --route GET:/payments    # filter by route
switchly log --page 2                 # next page
switchly log --per-page 50           # 50 rows per page
```

| Option | Description |
|---|---|
| `--route ROUTE` | Filter entries to a single route key |
| `--page INT` | Page number to display (default: 1) |
| `--per-page INT` | Rows per page (default: 20) |

---

## Config commands

### `switchly config set-url`

Override the server URL and save it to `~/.switchly/config.json`. All subsequent commands will use this URL.

```bash
switchly config set-url http://prod.example.com/switchly
```

---

### `switchly config show`

Display the resolved server URL, its source (env var, `.switchly` file, or config file), and the current auth session status.

```bash
switchly config show
```

---

## Server URL discovery

The CLI resolves the server URL using the following priority order — highest wins:

| Priority | Source | Example |
|---|---|---|
| 1 (highest) | `SWITCHLY_SERVER_URL` environment variable | `export SWITCHLY_SERVER_URL=http://...` |
| 2 | `SWITCHLY_SERVER_URL` in a `.switchly` file (walked up from the current directory) | `.switchly` file in project root |
| 3 | `server_url` in `~/.switchly/config.json` | Set via `switchly config set-url` |
| 4 (default) | Hard-coded default | `http://localhost:8000/switchly` |

!!! tip "Commit a `.switchly` file"
    Add a `.switchly` file to your project root so the whole team automatically uses the correct server URL without manual configuration:

    ```ini title=".switchly"
    SWITCHLY_SERVER_URL=http://localhost:8000/switchly
    ```

---

## Route key format

Routes are identified by a method-prefixed key. Use the same format in all CLI commands.

| Decorator | Route key |
|---|---|
| `@router.get("/payments")` | `GET:/payments` |
| `@router.post("/payments")` | `POST:/payments` |
| `@router.get("/api/v1/users")` | `GET:/api/v1/users` |

```bash
switchly disable "GET:/payments"    # specific method
switchly enable "/payments"         # applies to all methods registered under /payments
```

---

## Token storage

Auth tokens are stored in a JSON file at a platform-specific location:

| Platform | Location |
|---|---|
| macOS / Linux | `~/.switchly/config.json` |
| Windows | `%USERPROFILE%\AppData\Local\switchly\config.json` |

The config file stores the server URL, the current token, the username, and the token expiry timestamp. Delete this file to clear all credentials.
