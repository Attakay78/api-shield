# Installation

## Requirements

- Python **3.11** or higher
- A supported web framework — **FastAPI** is currently supported; more framework adapters are on the way

---

## Install with uv (recommended)

```bash
# Minimal — core library only (no framework adapter, no CLI, no dashboard)
uv add switchly

# FastAPI adapter
uv add "switchly[fastapi]"

# FastAPI + CLI
uv add "switchly[fastapi,cli]"

# FastAPI + rate limiting
uv add "switchly[fastapi,rate-limit]"

# FastAPI + feature flags
uv add "switchly[fastapi,flags]"

# Everything (FastAPI adapter, Redis, dashboard, CLI, admin, rate limiting)
uv add "switchly[all]"
```

## Install with pip

```bash
pip install "switchly[all]"
```

---

## Optional extras

| Extra | What it adds | When to use |
|---|---|---|
| `fastapi` | FastAPI adapter (middleware, decorators, router, OpenAPI integration) | FastAPI apps |
| `redis` | `RedisBackend` for multi-instance deployments | Production with multiple replicas |
| `dashboard` | Jinja2 + aiofiles for the HTMX dashboard | When mounting the admin UI |
| `admin` | Unified `SwitchlyAdmin` (dashboard + REST API) | Recommended for CLI support |
| `cli` | `switchly` command-line tool + httpx client | Operators managing routes from the terminal |
| `rate-limit` | `limits` library for `@rate_limit` enforcement | Any app using rate limiting |
| `flags` | `openfeature-sdk` + `packaging` for the feature flag system | Any app using feature flags |
| `all` | All of the above | Easiest option for most projects |

---

## Verify the installation

```bash
# Check the library is importable
python -c "import switchly; print(switchly.__version__)"

# Check the CLI is available
switchly --help
```

---

## Environment variables

switchly can be configured through environment variables so no code changes are needed between environments:

| Variable | Default | Description |
|---|---|---|
| `SWITCHLY_BACKEND` | `memory` | Backend type: `memory`, `file`, or `redis` |
| `SWITCHLY_ENV` | `dev` | Current environment name (used by `@env_only`) |
| `SWITCHLY_FILE_PATH` | `switchly-state.json` | Path for `FileBackend` |
| `SWITCHLY_REDIS_URL` | `redis://localhost:6379/0` | URL for `RedisBackend` |

Or commit a `.switchly` file in your project root; both the app and the CLI discover it automatically:

```ini
# .switchly
SWITCHLY_BACKEND=file
SWITCHLY_FILE_PATH=switchly-state.json
SWITCHLY_ENV=dev
SWITCHLY_SERVER_URL=http://localhost:8000/switchly
```

---

## Next steps

- [**Tutorial: Your first decorator →**](first-decorator.md)
- [**Tutorial: Feature Flags →**](feature-flags.md)
