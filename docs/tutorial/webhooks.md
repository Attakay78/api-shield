# Webhooks

Webhooks fire an HTTP POST to a URL whenever a route's state changes. Use them to notify a Slack channel, trigger a CI pipeline, or update a status page.

---

## Registering a webhook

```python
from waygate import make_engine

engine = make_engine()
await engine.add_webhook("https://hooks.example.com/route-events")
```

Every state change sends a POST to the URL with a JSON body.

---

## Default payload

```json
{
  "event": "maintenance_on",
  "path": "GET:/payments",
  "reason": "Database migration",
  "timestamp": "2025-06-01T03:00:00.000Z",
  "state": {
    "status": "maintenance",
    "reason": "Database migration",
    "enabled": true,
    ...
  }
}
```

The `event` field identifies what happened:

| Event | Trigger |
|---|---|
| `maintenance_on` | Route put into maintenance |
| `maintenance_off` | Route taken out of maintenance |
| `enable` | Route enabled |
| `disable` | Route disabled |
| `env_gate` | Route restricted to specific environments |

---

## Slack notifications

Waygate includes a built-in Slack formatter. Pass `SlackWebhookFormatter()` as the `formatter` argument:

```python
from waygate.core.webhooks import SlackWebhookFormatter

await engine.add_webhook(
    "https://hooks.slack.com/services/T00000000/B00000000/XXXX",
    formatter=SlackWebhookFormatter(),
)
```

Sends a colour-coded Slack attachment per event: orange for maintenance, red for disable, green for enable.

---

## Custom formatter

A formatter is any callable that takes `(event, path, state)` and returns a dict, which is serialised to JSON and posted to the URL.

```python
from waygate.core.models import RouteState

def pagerduty_formatter(event: str, path: str, state: RouteState) -> dict:
    return {
        "routing_key": "your-pagerduty-routing-key",
        "event_action": "trigger" if "off" not in event else "resolve",
        "payload": {
            "summary": f"{event}: {path}",
            "severity": "warning",
            "source": "waygate",
            "custom_details": {"reason": state.reason},
        },
    }

await engine.add_webhook(
    "https://events.pagerduty.com/v2/enqueue",
    formatter=pagerduty_formatter,
)
```

---

## Multiple webhooks

Register as many webhooks as you need. Each fires independently for every state change.

```python
await engine.add_webhook("https://hooks.slack.com/...", formatter=SlackWebhookFormatter())
await engine.add_webhook("https://status-page.example.com/webhook")
await engine.add_webhook("https://ci.example.com/trigger")
```

---

## Registering at startup

Register webhooks inside a FastAPI lifespan so they are ready before the first request:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from waygate import make_engine
from waygate.fastapi import WaygateMiddleware

engine = make_engine()

@asynccontextmanager
async def lifespan(_):
    await engine.add_webhook("https://hooks.slack.com/...", formatter=SlackWebhookFormatter())
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(WaygateMiddleware, engine=engine)
```

---

## Delivery behaviour

Webhooks fire asynchronously. If the target URL is unavailable, the event is dropped after one attempt. For guaranteed delivery, place a durable queue (e.g. Redis Streams, SQS) in front of the webhook consumer and handle retries there.

---

## Next step

[**Tutorial: Audit Log**](audit-log.md)
