# Audit Log

The audit log records every state change: who made it, when, what route was affected, and the before/after status.

---

## What gets recorded

An entry is written whenever:

- A route's status changes (maintenance on/off, enable, disable, env-gate)
- A global maintenance window is activated or deactivated
- A rate limit policy is created, updated, or deleted
- A feature flag is created, updated, or deleted
- A segment is created, updated, or deleted

Each entry captures:

| Field | Description |
|---|---|
| `path` | The route key, e.g. `GET:/payments` |
| `action` | What happened, e.g. `maintenance_on`, `enable`, `disable` |
| `actor` | Who made the change (`"system"` for decorator-driven changes, or a username from the CLI or dashboard) |
| `platform` | Where the change came from (`"cli"`, `"dashboard"`, `"api"`, or `""`) |
| `old_status` | Route status before the change |
| `new_status` | Route status after the change |
| `reason` | The reason string, if one was provided |
| `timestamp` | UTC timestamp of the change |

---

## Viewing the audit log

### Dashboard

Open the admin dashboard and click the **Audit** tab. Filter by route path and scroll through the history. Each row shows the actor, platform, action, and timestamp.

### CLI

```bash
# Last 20 entries across all routes
waygate audit

# Filter to a specific route
waygate audit GET:/payments

# Increase the limit
waygate audit --limit 100
```

### Engine API

```python
# All entries (last 100 by default)
entries = await engine.get_audit_log()

# Filter to a specific route
entries = await engine.get_audit_log(path="GET:/payments")

# Increase the limit
entries = await engine.get_audit_log(limit=500)

for entry in entries:
    print(entry.timestamp, entry.actor, entry.action, entry.path)
```

---

## Reading an entry

```python
from waygate.core.models import AuditEntry

entries = await engine.get_audit_log(path="GET:/payments")
entry: AuditEntry = entries[0]

print(entry.path)        # "GET:/payments"
print(entry.action)      # "maintenance_on"
print(entry.actor)       # "admin"
print(entry.platform)    # "dashboard"
print(entry.old_status)  # "active"
print(entry.new_status)  # "maintenance"
print(entry.reason)      # "Database migration"
print(entry.timestamp)   # datetime(2025, 6, 1, 3, 0, tzinfo=UTC)
```

---

## Suppressing audit entries

Pass `audit=False` to suppress entries for programmatic changes at startup, such as seeding flags or registering routes:

```python
@asynccontextmanager
async def lifespan(_):
    await engine.save_flag(FeatureFlag(key="new-checkout", ...), audit=False)
    await engine.save_segment(Segment(key="beta-users", ...), audit=False)
    yield
```

Changes made through the dashboard, CLI, or REST API always create audit entries.

---

## Storage

Audit entries are stored in the active backend alongside route state.

| Backend | Audit storage | Notes |
|---|---|---|
| `MemoryBackend` | In-process list | Lost on restart |
| `FileBackend` | Appended to the state file | Survives restarts |
| `RedisBackend` | Redis list | Shared across all workers |

For long-term retention, export entries periodically to your own datastore.

---

## Next step

[**Tutorial: Admin Dashboard**](admin-dashboard.md)
