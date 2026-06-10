# Setup

Install the `infrared-sdk` package and authenticate the client. Auth uses an `X-Api-Key` header populated from the `INFRARED_API_KEY` env var.

## Setup

```bash
pip install infrared-sdk
# or: uv add infrared-sdk

# Optional: faster tile decoding (orjson, ~2.2× faster; stdlib fallback is identical)
pip install "infrared-sdk[fast]"
# or: uv add "infrared-sdk[fast]"
```

`.env` (loaded automatically via `python-dotenv` at module import):

```dotenv
INFRARED_API_KEY=your-key-here
# Optional tuning
# INFRARED_BASE_URL=https://api.infrared.city/v2   # override base URL (must include /v2)
# INFRARED_BIG_PAYLOADS_ENABLED=true                # default true — auto-switch >5 MiB POSTs to $ref envelope
# INFRARED_BIG_PAYLOADS_THRESHOLD_BYTES=5242880     # override the auto-switch threshold
# INFRARED_QUIET=1                                  # silence the startup banner + agent-discoverability log line
#                                                   # NOTE (0.4.10): [INFO]/[WARN] [SDK:...] diagnostic lines are NOT
#                                                   # suppressed by INFRARED_QUIET — no suppression flag exists yet.
```

```python
from infrared_sdk import InfraredClient

# Reads INFRARED_API_KEY from env. Default base URL is https://api.infrared.city/v2.
with InfraredClient() as client:
    ...

# Or explicit
client = InfraredClient(api_key="your-key")
# Override base URL via INFRARED_BASE_URL env var — must include /v2 if set manually.

# Localhost / host-only gateways (0.4.10+): pass base_url directly; /v2 is NOT required.
client = InfraredClient(api_key="your-key", base_url="http://localhost:8000/api")
```

Full SDK reference: <https://infrared.city/docs/sdk>.

## Auth header

The SDK sends `X-Api-Key: <your-key>` on every request. Get a key at [infrared.city](https://infrared.city). Requires Python 3.9+.

## Pitfalls

- Use the context manager (`with InfraredClient() as client:`) or call `client.close()` to release the HTTP session.
- Do not commit `.env` — keep `INFRARED_API_KEY` out of source control.
- The package name is `infrared-sdk` (PyPI) but the import is `infrared_sdk` (snake_case).
- `dotenv` is loaded best-effort; if it is not installed, set the env var manually before running.
- `InfraredClient()` without an env var or explicit `api_key` raises `ValueError: api_key is required. Pass it directly or set the INFRARED_API_KEY environment variable.`
- **`INFRARED_QUIET=1` does not suppress all SDK output (0.4.10).** It silences the startup banner and agent-discoverability line, but the always-on `[INFO]/[WARN] [SDK:...]` diagnostic lines are still printed to stdout. There is no suppression flag for them in 0.4.10.
- **`base_url` with localhost/gateway:** `InfraredClient(base_url="http://localhost:8000/api")` works without a `/v2` suffix. Only the default cloud endpoint requires `/v2` when set via `INFRARED_BASE_URL`.

## See also

- `01-quickstart.md` — minimum end-to-end run
- `02-geometry.md` — polygon format
- `04-weather-data.md` — weather station lookup
