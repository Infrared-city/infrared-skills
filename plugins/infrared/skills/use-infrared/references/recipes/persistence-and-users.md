# Recipe: many users, stored runs, no double bills

Use this page when more than one person uses your app. It adds four things to a working
app: sign-in, a run limit per user, stored results, and a cache, so that the same inputs
are never billed twice.

Start from one of the two app shapes. This page adds storage and users to both.

| App shape | Who runs the SDK | Start from |
|---|---|---|
| Browser app | The SDK in a Web Worker on each user's device; a proxy holds the key | [../typescript/cloudflare-proxy.md](../typescript/cloudflare-proxy.md) |
| Server app | Your Python service runs, merges and stores | [python-fastapi-app.md](python-fastapi-app.md) |

Guide chapter "Serve many users": <https://infrared.city/docs/sdk/1.0/sdk.md>.

## The rules

1. **The Infrared key bills your account.** It stays on your server. Each user signs in to
   *your* app; the proxy or the service adds the key.
2. **Check the user before every billed call.** The proxy or `POST /runs` checks the sign-in
   and the user's quota. Preview is free: allow it more often.
3. **Cache by input hash.** The API has no result cache. The same run again is billed again.
   Hash every input, and return the stored run for a known hash.
4. **Store the result, not the job.** Job results expire on the server. Save the merged
   result in your own storage when the run is done.
5. **Charge from the preview.** Reserve `would_bill_jobs` credits before the run. Give them
   back if the run fails.

## The tables

Four tables are enough. Put big files in a bucket, not in the database.

| Table | Key columns | Why |
|---|---|---|
| `users` | `id`, `email`, `credits` | Sign-in and balance |
| `runs` | `id`, `user_id`, `input_hash` (unique), `status`, `jobs`, `schedule_json`, `result_key`, `error` | One row per distinct run; the cache |
| `credit_ledger` | `user_id`, `delta`, `reason`, `ref` (unique with `reason`) | Every charge and refund, idempotent |
| `projects` (optional) | `id`, `user_id`, `name`, `polygon`, `state_json` | Sites, scenarios, UI state |

```python
# db.py: SQLAlchemy 2.x. The same code runs on SQLite and Postgres.
from datetime import datetime, timezone
from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

def now() -> datetime:
    return datetime.now(timezone.utc)

class Base(DeclarativeBase): ...

class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)   # who started it first
    input_hash: Mapped[str] = mapped_column(String(64), unique=True)  # the cache key
    analysis: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|running|done|failed
    jobs: Mapped[int] = mapped_column(Integer, default=0)             # from the preview
    schedule_json: Mapped[str | None] = mapped_column(Text)           # to resume after a restart
    result_key: Mapped[str | None] = mapped_column(String(255))       # blob with the result
    error: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class CreditLedger(Base):
    __tablename__ = "credit_ledger"
    __table_args__ = (UniqueConstraint("reason", "ref"),)             # one charge per run
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    delta: Mapped[int] = mapped_column(Integer)                       # -jobs, +refund, +purchase
    reason: Mapped[str] = mapped_column(String(32))                   # run | refund | purchase
    ref: Mapped[str] = mapped_column(String(128))                     # run id or payment id
```

Keep `users.credits` as a cached sum of the ledger, or compute it with `SUM(delta)`.

## The cache key

Hash everything that changes the result: the request, the polygon, every layer, and the
SDK version. Use canonical JSON (sorted keys, no spaces), so equal inputs give equal bytes.

```python
import hashlib, json
import infrared_sdk

def input_hash(request, polygon: dict, buildings=None, vegetation=None,
               ground_materials=None) -> str:
    blob = {
        "sdk": infrared_sdk.__version__,                         # a new SDK can change results
        "request": request.model_dump(mode="json"),             # includes weather and time period
        "terrain_alignment": getattr(request, "terrain_alignment", None),  # not in the dump for wind
        "polygon": polygon,
        "buildings": buildings, "vegetation": vegetation, "ground_materials": ground_materials,
    }
    text = json.dumps(blob, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode()).hexdigest()
```

- Hash the **own data the user sent**, not a public-data fetch. For a public-data run, hash
  the polygon and the analysis, and store the fetched buildings with the run.
- Round coordinates to a fixed precision before you hash, if your front end can send
  `16.3710000001` for the same point.
- A failed run must not block a retry: delete its row, or allow a new row when the old one
  has `status = "failed"`.

## Start a run: check, reserve, run, store

```python
import gzip, uuid
from sqlalchemy.exc import IntegrityError

def start_run(db, blobs, client, pool, user, request, polygon, buildings) -> dict:
    key = input_hash(request, polygon, buildings)
    with db.session() as s:
        if (old := s.query(Run).filter_by(input_hash=key).one_or_none()) and old.status != "failed":
            return {"run_id": old.id, "cached": True}            # same inputs: no new bill
        if old:
            s.delete(old)
        jobs = client.preview_area(polygon, payload=request, buildings=buildings).would_bill_jobs
        if balance(s, user.id) < jobs:
            raise PermissionError("not enough credits")          # HTTP 402 to your front end
        run = Run(id=uuid.uuid4().hex, user_id=user.id, input_hash=key,
                  analysis=request.analysis_type, jobs=jobs)
        s.add(run)
        s.add(CreditLedger(user_id=user.id, delta=-jobs, reason="run", ref=run.id))
        try:
            s.commit()                                           # unique input_hash: a parallel click loses here
        except IntegrityError:
            s.rollback()
            return {"run_id": s.query(Run).filter_by(input_hash=key).one().id, "cached": True}
        run_id = run.id                                          # read it while the session is open
    pool.submit(execute, db, blobs, client, run_id, request, polygon, buildings)
    return {"run_id": run_id, "cached": False}

def execute(db, blobs, client, run_id, request, polygon, buildings) -> None:
    try:
        result = client.run_area_and_wait(request, polygon, buildings=buildings)
        body = gzip.compress(json.dumps(result.to_dict()).encode())  # real values, null = no value
        blobs.put(f"results/{run_id}.json.gz", body, "application/gzip")
        update_run(db, run_id, status="done", result_key=f"results/{run_id}.json.gz")
    except Exception:
        log.exception("run %s failed", run_id)                   # details stay in the server log
        update_run(db, run_id, status="failed", error="run failed")
        refund(db, run_id)                                       # ledger row reason="refund", ref=run_id
```

Read a stored result back with `AreaResult.from_dict(json.loads(gzip.decompress(body)))`.
Then use `physical_grid()`, `bounds` and the legend as for a live result.

- **Facade and roof runs:** store the values with `columns.to_bytes(layout_key=...)` and the
  layout one time for each geometry (`layout.to_bytes()`). See "Save and reload" in the guide.
- **Long runs that must survive a deploy:** use `run_area` and store `schedule.to_dict()` in
  `schedule_json`. A start-up task resumes open runs ([../async-and-jobs.md](../async-and-jobs.md)).
- **Share results.** A run belongs to its input hash, not to one user. A second user with
  the same inputs gets the stored result. Decide if that is allowed in your app (public sites:
  usually yes; private designs: add `user_id` or a project id to the hash).

## The browser app (proxy) version

In the browser shape the SDK runs on the user's device, so the proxy is your only server.

- The Worker checks the session (your sign-in, or Supabase / Clerk / Auth.js JWT).
- It counts billed calls per user in a database (Cloudflare D1, or KV for a simple counter).
  A run of N tiles makes about 2 N POSTs (upload link and submit). Count the submits
  (`POST .../async/...`), not every request.
- Store results from the browser: send the decoded grid (`areaGridValuesF32(result)`) with
  `result.bounds` and the legend to your bucket through the Worker, keyed by the input hash.
  Before a run, ask the Worker for that hash first.
- Delete the `geometryUrlStore` at sign-out ([../building-fast-apps.md](../building-fast-apps.md)).

## Storage: pick one path

| | A: local | B: Postgres + S3 | C: Supabase |
|---|---|---|---|
| Database | SQLite file | Postgres (Railway, Neon, RDS) | Supabase Postgres |
| Bucket | folder on disk | any S3 API (R2, Railway Buckets, B2, S3) | Supabase Storage (S3 API) |
| Sign-in | none, or one shared password | your own | built in (magic link, OAuth) |
| Good for | a demo on one machine | a hosted app | sign-in without your own auth code |

One bucket class covers B and C. Only the endpoint and keys change:

```python
import os, boto3
from botocore.config import Config

class S3Blobs:
    def __init__(self) -> None:
        self.bucket = os.environ["BUCKET"]
        self.s3 = boto3.client("s3", endpoint_url=os.environ["S3_ENDPOINT"],
                               aws_access_key_id=os.environ["S3_KEY_ID"],
                               aws_secret_access_key=os.environ["S3_SECRET"],
                               region_name=os.environ.get("S3_REGION", "auto"),
                               config=Config(s3={"addressing_style": "path"}))
    def put(self, key: str, body: bytes, content_type: str) -> None:
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=body, ContentType=content_type)
    def get(self, key: str) -> bytes:
        return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
    def url(self, key: str, seconds: int = 3600) -> str:     # private bucket: signed GET link
        return self.s3.generate_presigned_url("get_object",
                                              Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=seconds)
```

- Path A on a container host loses the disk at each deploy. Mount a volume, or use B.
- Free Supabase projects pause after a week with no use.
- SQLite ignores `with_for_update()`. The unique constraints still protect you.

## Sign-in

Use a provider. Do not write password code for a demo.

- **Supabase:** magic link from the front end; verify the JWT in your API with the project's
  JWKS (`PyJWT` with `PyJWKClient`). Never trust a `user_id` sent by the browser.
- **Clerk, Auth0, Auth.js:** the same shape: verify the token on each request, then read
  the user id from it.
- **One-machine demo:** one shared password in an environment variable is enough.

## Payments (optional)

| Option | You get | Notes |
|---|---|---|
| Stripe Checkout + the ledger above | Credit packs | Webhook `checkout.session.completed` adds a `purchase` row with `ref = session id`. The unique `(reason, ref)` makes a repeated delivery harmless. You handle VAT (Stripe Tax). |
| Polar | Credit packs, VAT and sales tax handled (merchant of record) | Standard Webhooks v1; verify with the `standardwebhooks` library. Use `order.paid`, not `order.created`. |
| Stripe Billing Meters | Pay per run, monthly invoice | Send one meter event per run instead of a ledger. |

Webhook rules for every provider: verify the signature on the raw body, answer fast, and
make the handler idempotent with a unique key on the payment id.

## Pitfalls

- A cache key without the SDK version or without the weather returns an old result for a
  new question.
- Charging per tile in your UI but per job in the ledger: always use `would_bill_jobs`.
- A retry loop around `run_area_and_wait`: the SDK already retries. A second loop can pay twice.
- In-place edits of a JSON column are not seen by SQLAlchemy. Assign a new value, or use `MutableDict`.
- Error text from the SDK can hold details that users must not see. Log it; send a short message.

## Check before you call it done

- [ ] The same inputs from two users or two clicks give one run and one ledger charge.
- [ ] A failed run gives the credits back, and the same inputs can run again.
- [ ] A stored result reloads after a restart and draws the same map.
- [ ] No Infrared key in the front end, the logs or a response.
