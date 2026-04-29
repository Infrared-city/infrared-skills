# Setup

Install the `infrared-sdk` package and authenticate the client. Auth uses an `X-Api-Key` header populated from the `INFRARED_API_KEY` env var.

## Setup

```bash
pip install infrared-sdk
# or: uv add infrared-sdk
```

`.env` (loaded automatically via `python-dotenv` at module import):

```dotenv
INFRARED_API_KEY=your-key-here
```

```python
from infrared_sdk import InfraredClient

# Reads INFRARED_API_KEY from env. The SDK ships with the correct production base URL.
with InfraredClient() as client:
    ...

# Or explicit
client = InfraredClient(api_key="your-key")
```

Full SDK reference: <https://infrared.city/docs/sdk>.

## Auth header

The SDK sends `X-Api-Key: <your-key>` on every request. Get a key at [infrared.city](https://infrared.city). Requires Python 3.11+.

## Pitfalls

- Use the context manager (`with InfraredClient() as client:`) or call `client.close()` to release the HTTP session.
- Do not commit `.env` — keep `INFRARED_API_KEY` out of source control.
- The package name is `infrared-sdk` (PyPI) but the import is `infrared_sdk` (snake_case).
- `dotenv` is loaded best-effort; if it is not installed, set the env var manually before running.
- `InfraredClient()` without an env var or explicit `api_key` raises `ValueError: api_key is required. Pass it directly or set the INFRARED_API_KEY environment variable.`

## See also

- `01-quickstart.md` — minimum end-to-end run
- `02-geometry.md` — polygon format
- `04-weather-data.md` — weather station lookup
