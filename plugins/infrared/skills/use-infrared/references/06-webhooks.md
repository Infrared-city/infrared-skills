# Webhooks

Register webhook endpoints to receive job status notifications instead of polling. Useful for long-running area runs and async pipelines.

## Register and submit

```python
from infrared_sdk import InfraredClient
from infrared_sdk.webhooks.service import WebhooksServiceClient
from infrared_sdk import WEBHOOK_EVENT_SUCCEEDED, WEBHOOK_EVENT_FAILED

with InfraredClient() as client:
    # Register an endpoint (type: "production" or "development")
    endpoint = client.webhooks.register(
        url="https://your-server.com/webhooks",
        type="production",
    )
    print(f"Endpoint ID: {endpoint.id}")

    # List all endpoints
    endpoints = client.webhooks.list()

    # Submit a job with webhook notification
    job = client.run(
        payload,
        webhook_url="https://your-server.com/webhooks",
        webhook_events=[WEBHOOK_EVENT_SUCCEEDED, WEBHOOK_EVENT_FAILED],
    )

    # Delete an endpoint
    client.webhooks.delete(endpoint.id)
```

`client.webhooks.register()` returns a `WebhookEndpoint(id, url, type, created_at, updated_at)`. The same `webhook_url` / `webhook_events` kwargs are accepted by `run_area_and_wait()` and `run_area()`.

## Event types

| Constant                    | Event string      | Fired when                |
| --------------------------- | ----------------- | ------------------------- |
| `WEBHOOK_EVENT_RUNNING`     | `job.running`     | Job has started executing |
| `WEBHOOK_EVENT_SUCCEEDED`   | `job.succeeded`   | Job completed             |
| `WEBHOOK_EVENT_FAILED`      | `job.failed`      | Job failed                |

Subscribe by passing a list to `webhook_events`. Empty / omitted means subscribe to nothing — register but no deliveries.

## Verifying signatures

```python
is_valid = WebhooksServiceClient.verify_signature(
    payload_body=request_body,
    headers=request_headers,
    secret="your-webhook-secret",
    tolerance=300,  # seconds
)
```

`verify_signature` is a classmethod — call it without instantiating. `tolerance` is the max age of the timestamp header in seconds; reject anything older to prevent replay.

## Pitfalls

- Multi-payload area runs fan out: `payloads x tiles` events arrive in a tight burst. Buffer ingestion (queue, batch DB writes) — don't write per-event.
- A registered endpoint receives only the events you listed in `webhook_events` per submission, not every job in the workspace.
- `WebhookRegistrationError` and `WebhookNotFoundError` (both subclass `WebhookError`) are raised for register/delete failures — wrap accordingly.
- Endpoint `type` must be `"production"` or `"development"` — other strings reject.
- The registration response only returns `{id, url, type}`; `created_at`/`updated_at` populate only when fetched via `list()` / `get()`.
- Treat the webhook secret as scoped: never commit it, never reuse a per-script token elsewhere.

## See also

- `references/workflows/area-api.md` — multi-payload burst sizing
- `references/workflows/errors.md` — webhook exception hierarchy
- `references/01-quickstart.md` — submitting jobs the polling way
