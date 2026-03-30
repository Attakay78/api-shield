# CLI

The `switchly` CLI is a thin HTTP client that talks to a running `SwitchlyAdmin` instance over HTTP. Install it separately if you only need the command-line tool:

```bash
uv add "switchly[cli]"
```

---

## First-time setup

### 1. Start your app with SwitchlyAdmin mounted

```python title="main.py"
app.mount("/switchly", SwitchlyAdmin(engine=engine, auth=("admin", "secret")))
```

### 2. Configure the server URL

Drop a `.switchly` file in your project root (commit it alongside your code so the whole team gets the right URL automatically):

```ini title=".switchly"
SWITCHLY_SERVER_URL=http://localhost:8000/switchly
```

Or set it manually:

```bash
switchly config set-url http://localhost:8000/switchly
```

### 3. Log in

```bash
switchly login admin
# Password: ••••••
```

Credentials are stored in `~/.switchly/config.json` with an expiry timestamp.

---

## Route management

```bash
switchly status                          # show all registered routes
switchly status GET:/payments            # inspect one route

switchly enable GET:/payments            # restore to ACTIVE
switchly disable GET:/payments --reason "Use /v2/payments instead"

switchly maintenance GET:/payments --reason "DB migration"

switchly maintenance GET:/payments \
  --reason "Planned migration" \
  --start 2025-06-01T02:00Z \
  --end   2025-06-01T04:00Z

switchly schedule GET:/payments \
  --start 2025-06-01T02:00Z \
  --end   2025-06-01T04:00Z \
  --reason "Planned migration"

switchly disable GET:/payments --reason "hotfix" --until 2h
```

??? example "Sample `switchly status` output"

    | Route | Status | Reason | Since |
    |---|---|---|---|
    | GET /payments | MAINTENANCE | DB migration | 2 hours ago |
    | GET /debug | ENV_GATED | dev, staging only | startup |
    | GET /health | ACTIVE | | |

---

## Global maintenance

```bash
switchly global enable --reason "Deploying v2"

# Exempt specific paths so they keep responding
switchly global enable --reason "Deploying v2" --exempt /health --exempt GET:/status

# Block even @force_active routes
switchly global enable --reason "Hard lockdown" --include-force-active

# Adjust exemptions while active
switchly global exempt-add /monitoring/ping
switchly global exempt-remove /monitoring/ping

switchly global status    # check current state
switchly global disable   # restore normal operation
```

---

## Environment gating

Restrict a route to specific environments at runtime without redeploying.

```bash
switchly env set /api/debug dev                    # allow only the "dev" environment
switchly env set /api/internal dev staging         # allow dev and staging
switchly env clear /api/debug                      # remove the gate, restore to ACTIVE
```

!!! note
    The engine's `current_env` is set at startup (`SwitchlyEngine(current_env="prod")`). Requests from an environment not in `allowed_envs` receive a `403 ENV_GATED` response. `switchly env clear` is equivalent to calling `switchly enable` — it transitions the route back to `ACTIVE`.

---

## Multi-service context

When the Switchly Server manages multiple services, scope every command to the right service.

### Option A — `SWITCHLY_SERVICE` env var (recommended)

```bash
export SWITCHLY_SERVICE=payments-service
switchly status               # only payments-service routes
switchly disable GET:/payments --reason "hotfix"
switchly enable  GET:/payments
```

All route commands (`status`, `enable`, `disable`, `maintenance`, `schedule`) read `SWITCHLY_SERVICE` automatically. An explicit `--service` flag always overrides it.

### Option B — `--service` flag per command

```bash
switchly status --service payments-service
switchly disable GET:/payments --service payments-service --reason "hotfix"
```

### Discover active context and connected services

```bash
switchly current-service          # show which service SWITCHLY_SERVICE points to
switchly services                 # list all services registered with the Switchly Server
```

??? example "Sample `switchly services` output"

    ```
    Connected services
    ┌──────────────────────┐
    │ Service              │
    ├──────────────────────┤
    │ orders-service       │
    │ payments-service     │
    └──────────────────────┘
    ```

---

## Rate limits

Manage rate limit policies and view blocked requests. Requires `switchly[rate-limit]` on the server.

`switchly rl` and `switchly rate-limits` are aliases — use whichever you prefer.

```bash
switchly rl list                              # show all registered policies
switchly rl set GET:/public/posts 20/minute   # set or update a policy
switchly rl set GET:/search 5/minute --algorithm fixed_window --key global
switchly rl reset GET:/public/posts           # clear counters immediately
switchly rl delete GET:/public/posts          # remove persisted policy override
switchly rl hits                              # blocked requests log, page 1
switchly rl hits --page 2                     # next page
switchly rl hits --per-page 50               # 50 rows per page

# identical — switchly rate-limits is the full name
switchly rate-limits list
switchly rate-limits set GET:/public/posts 20/minute
```

!!! tip "SDK clients receive policy changes in real time"
    When using Switchly Server + SwitchlySDK, rate limit policies set via `switchly rl set` are broadcast over the SSE stream and applied to every connected SDK client immediately — no restart required.

??? example "Sample `switchly rl list` output"

    | Route | Limit | Algorithm | Key Strategy |
    |---|---|---|---|
    | GET /public/posts | 10/minute | fixed_window | ip |
    | GET /search | 5/minute | fixed_window | global |
    | GET /users/me | 100/minute | fixed_window | user |

---

## Audit log

```bash
switchly log                          # page 1, 20 entries per page
switchly log --route GET:/payments    # filter by route
switchly log --page 2                 # next page
switchly log --per-page 50           # 50 rows per page
```

??? example "Sample `switchly log` output"

    | Timestamp | Route | Action | Actor | Platform | Status | Reason |
    |---|---|---|---|---|---|---|
    | 2025-06-01 02:00:01 | GET:/payments | maintenance | alice | cli | active > maintenance | DB migration |
    | 2025-06-01 01:59:00 | GET:/debug | disable | system | system | active > disabled | |
    | 2025-06-01 01:58:00 | GET:/payments | rl_policy_set | alice | cli | set | |

---

## Auth commands

```bash
switchly login admin                          # prompts for password interactively
switchly login admin --password "$SWITCHLY_PASS"  # inline, useful in CI

switchly config show   # check current session and resolved URL
switchly logout        # revokes server-side token and clears local credentials
```

---

## Config commands

```bash
switchly config set-url http://prod.example.com/switchly   # override server URL
switchly config show                                      # show URL, source, session
```

---

## Server URL discovery

The CLI resolves the server URL using this priority order (highest wins):

| Priority | Source | How to set |
|---|---|---|
| 1 | `SWITCHLY_SERVER_URL` environment variable | `export SWITCHLY_SERVER_URL=http://...` |
| 2 | `SWITCHLY_SERVER_URL` in a `.switchly` file (walked up from cwd) | Add to project root |
| 3 | `server_url` in `~/.switchly/config.json` | `switchly config set-url ...` |
| 4 | Default | `http://localhost:8000/switchly` |

---

## Route key format

Routes are identified by a method-prefixed key. Use the same format in all CLI commands:

| Decorator | Route key |
|---|---|
| `@router.get("/payments")` | `GET:/payments` |
| `@router.post("/payments")` | `POST:/payments` |
| `@router.get("/api/v1/users")` | `GET:/api/v1/users` |

```bash
switchly disable "GET:/payments"   # method-specific
switchly enable "/payments"        # applies to all methods under /payments
```

---

## Next step

Dive into the full [**Reference documentation →**](../reference/decorators.md)
