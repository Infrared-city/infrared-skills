# Webhooks

Receive job-lifecycle notifications instead of polling. The SDK implements the Standard Webhooks v1 contract: HMAC-SHA256 signed deliveries, replay-protection headers, three job event types.

There are two layers — keep them separate in your head:

1. **Endpoint registration** (once per environment, dashboard-managed signing secret) — `client.webhooks.register(...)`.
2. **Per-submission subscription** (which events you want for a specific job/area run) — `webhook_url=` / `webhook_events=` on `run_area()` / `run_area_and_wait()`.

A registered endpoint receives only the events you subscribe to per submission. Registering alone delivers nothing.

## Endpoint registration

```python
from infrared_sdk import InfraredClient

with InfraredClient() as client:
    endpoint = client.webhooks.register(
        url="https://your-server.com/webhooks",
        type="production",   # "production" or "development"
    )
    print(endpoint.id)

    endpoints = client.webhooks.list()        # list[WebhookEndpoint]
    client.webhooks.delete(endpoint.id)
```

`type` selects the **server-side environment** (and signing-secret pair) the endpoint is bound to: `"production"` for production traffic, `"development"` for staging / dev. The signing secret is shown in the dashboard at `https://app.infrared.city` after registration — copy it as-is (it starts with `whsec_`).

`register()` returns a `WebhookEndpoint(id, url, type, created_at, updated_at)`. Only `id`/`url`/`type` are populated on registration; `created_at`/`updated_at` come back from `list()` / `get()`.

## Per-submission subscription

```python
from infrared_sdk import (
    InfraredClient,
    WEBHOOK_EVENT_RUNNING,
    WEBHOOK_EVENT_SUCCEEDED,
    WEBHOOK_EVENT_FAILED,
)

with InfraredClient() as client:
    area = client.buildings.get_area(polygon)

    # Sync — returns AreaResult, also streams events
    result = client.run_area_and_wait(
        payload, polygon,
        buildings=area.buildings,
        webhook_url="https://your-server.com/webhooks",
        webhook_events=[WEBHOOK_EVENT_SUCCEEDED, WEBHOOK_EVENT_FAILED],
    )

    # Async — returns AreaSchedule immediately; merge later
    schedule = client.run_area(
        payload, polygon,
        buildings=area.buildings,
        webhook_url="https://your-server.com/webhooks",
        webhook_events=[WEBHOOK_EVENT_SUCCEEDED, WEBHOOK_EVENT_FAILED],
    )
```

Empty / omitted `webhook_events` means subscribe to nothing — no deliveries.

### Event types

| Constant                  | Wire value      | Fired when                  |
| ------------------------- | --------------- | --------------------------- |
| `WEBHOOK_EVENT_RUNNING`   | `job.running`   | Job has started executing   |
| `WEBHOOK_EVENT_SUCCEEDED` | `job.succeeded` | Job completed; results ready |
| `WEBHOOK_EVENT_FAILED`    | `job.failed`    | Job failed (error in payload) |

Prefer the constants over typing the strings — fewer typos, IDE autocomplete.

## Signature verification

Every delivery carries three headers — `webhook-id`, `webhook-timestamp`, `webhook-signature` — signed with HMAC-SHA256 over `{webhook-id}.{webhook-timestamp}.{body}`.

```python
from infrared_sdk import WebhooksServiceClient

is_valid = WebhooksServiceClient.verify_signature(
    payload_body=request_body,    # raw bytes from the HTTP request body
    headers=request_headers,
    secret="whsec_...",            # dashboard-copied secret, prefix included
    tolerance=300,                 # max timestamp age in seconds (replay window)
)
```

`verify_signature` is a `@staticmethod` — call it on the class without instantiating.

- **Pass raw request bytes, not parsed JSON.** This is the most common cause of verification failure: re-serialising the JSON (different whitespace, key order, escaping) changes the bytes and breaks the HMAC. In Flask use `request.get_data()`; in FastAPI `await request.body()`. Do **not** use `request.json` then `json.dumps(...)`.
- **Pass the secret as the dashboard gives it** — the `whsec_` prefix is stripped internally before HMAC computation. No manual decoding needed.
- **`tolerance`** is the maximum age of the `webhook-timestamp` header in seconds; deliveries older than that are rejected as replays. Default 300 s (5 min). Set `tolerance=0` to disable replay protection (not recommended).

## Idempotency

Deliveries are **best-effort with retries** on transient failures, so the same event can arrive more than once. Consumers must apply forward-only state transitions and ignore events that move a job backwards:

```
pending → running → succeeded
                 \→ failed
```

A `job.running` arriving after `job.succeeded` is a duplicate / out-of-order delivery — ignore it. The async demo's SQLite handler in `demos/areas_demo_async/` is the canonical pattern: store a status column, only update if the new status is forward in the ordering above.

## Multi-payload burst sizing

A multi-analysis or parameter-sweep area run delivers `payloads × tiles` events into a tight window — much denser than per-payload sequential submission. Buffer the ingest:

- Drop deliveries onto a queue (Redis / SQS / in-process `asyncio.Queue`) before doing DB work.
- Batch DB writes — one row per event in a hot loop will pin a worker and drop deliveries.
- Return `200` from the receiver as fast as possible; do work after acknowledging.

## Exception types

| Exception                   | Raised when                                         |
| --------------------------- | --------------------------------------------------- |
| `WebhookRegistrationError`  | `register()` HTTP call fails                        |
| `WebhookNotFoundError`      | `get(id)` / `delete(id)` returns 404                |
| `WebhookError`              | Base class for both, plus generic list/get failures |

All three are importable from `infrared_sdk` top-level. HTTP context lives on `.status_code` and `.response_body` attributes (not in the message string), so wrap log statements accordingly.

## Pitfalls

- **Verifying against re-encoded JSON.** Use the raw request bytes — see Signature verification above.
- **Endpoint `type` other than `"production"` / `"development"`** rejects at registration.
- **Treating the secret like a public token.** Store server-side, never commit, never expose to browsers.
- **Per-event DB writes during a burst.** Buffer or batch — see Multi-payload burst sizing above.
- **Out-of-order deliveries treated as authoritative.** Apply forward-only state transitions — see Idempotency above.

## See also

- `async-and-jobs.md` — `AreaSchedule`, manual polling via `check_area_state`, persist/resume, single-tile primitives
- `05-area-api.md` — multi-payload area submissions
- `08-error-handling.md` — full exception hierarchy
- `01-quickstart.md` — synchronous polling baseline
