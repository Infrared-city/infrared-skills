# Recipe: Persistence, Users, and Billing for an Infrared App

One simple shape — **two tables (`projects`, `artifacts`) + one blob bucket + one bindings interface** — that grows from "SQLite on my laptop" today to "Postgres + S3 + Auth + Stripe" tomorrow without rewriting call sites.

**The atomic unit of work depends on your app.** For a single-baseline tool (one geometry, one set of inputs, one set of results) the **project** is the atom and you can ignore scenarios entirely. For compare-the-options tools (baseline vs proposed design, hot day vs cold day) the **scenario** is the atom — multiple per project, each with its own inputs and result artifacts. The schema below supports both: every artifact carries an optional `scenario_id` (NULL = project-level), and scenarios live as a JSON list inside the project's `state_json` until you outgrow that and lift them into their own table.

This is the storage layer underneath [`python-fastapi-railway.md`](python-fastapi-railway.md). The frontend pieces in [`typescript-frontend-patterns.md`](typescript-frontend-patterns.md) talk to it via HTTP.

## What you get

- **Two tables** that cover everything: `projects` (your domain object) and `artifacts` (inputs + results + annotations, generic by kind/subtype).
- **One blob bucket** for big files (geojson, dotbim, png, gzipped sim results).
- **One swap point** — a `StorageBindings` interface — so today is SQLite + local-fs, tomorrow is Postgres + Railway Buckets, with the same routes.
- **Three deployment paths** with concrete code: hackathon SQLite, Railway all-in, Supabase all-in.
- **A users + credit-ledger schema** ready to layer auth and Stripe billing on top.

## Target Stack

- Python 3.11+, FastAPI (continues from [`python-fastapi-railway.md`](python-fastapi-railway.md)).
- `sqlalchemy>=2.0` + `alembic` for schema; works against SQLite, Postgres, MySQL with one connection-string change.
- `boto3` for S3-compatible blob storage (works for Railway Buckets, Backblaze B2, R2, Supabase Storage S3 endpoint).
- Path A: nothing else. Path B: Railway. Path C: Supabase + `supabase-py`.

## The two-table schema

```python
# app/db/schema.py
import uuid
from datetime import datetime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, Index


class Base(DeclarativeBase): ...


def _uuid() -> str:
    return uuid.uuid4().hex


# `scale` is an enum-checked hint for the UI (more / less detail at different zoom levels).
class Project(Base):
    __tablename__ = "projects"
    id:           Mapped[str]      = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id:      Mapped[str]      = mapped_column(String(64), index=True)
    name:         Mapped[str]      = mapped_column(String(255))
    scale:        Mapped[str]      = mapped_column(String(16), default="building")  # 'region' | 'city' | 'building'
    centroid_json: Mapped[str]     = mapped_column(Text)      # {"lat":..., "lon":...}
    boundary_json: Mapped[str|None] = mapped_column(Text, nullable=True)  # GeoJSON polygon
    state_json:   Mapped[str]      = mapped_column(Text, default="{}")
    # ^ holds scenarios, active scenario id, UI state — anything nested
    created_at:   Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at:   Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at:   Mapped[datetime|None] = mapped_column(DateTime, nullable=True, index=True)


class Artifact(Base):
    __tablename__ = "artifacts"
    id:           Mapped[str]      = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id:   Mapped[str]      = mapped_column(String(32), index=True)
    scenario_id:  Mapped[str|None] = mapped_column(String(32), nullable=True, index=True)
    kind:         Mapped[str]      = mapped_column(String(32))      # input | result | annotation
    subtype:      Mapped[str]      = mapped_column(String(64))      # buildings | sun-hours | pin
    format:       Mapped[str]      = mapped_column(String(32))      # geojson | dotbim | png | json
    status:       Mapped[str]      = mapped_column(String(16), default="ready")  # pending|ready|failed
    blob_key:     Mapped[str|None] = mapped_column(String(255), nullable=True)
    params_json:  Mapped[str]      = mapped_column(Text, default="{}")
    idempotency_key: Mapped[str]   = mapped_column(String(64))
    created_at:   Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    deleted_at:   Mapped[datetime|None] = mapped_column(DateTime, nullable=True, index=True)

    __table_args__ = (
        Index("ix_artifacts_lookup", "project_id", "kind", "subtype", "scenario_id"),
        Index("uq_artifacts_idempotency", "project_id", "idempotency_key", unique=True),
    )
```

Why two tables and JSON-blobs instead of fully normalised: scenarios, layers, and result-overlays all nest. Cramming them into rigid tables is a yak-shave that you'll undo when product changes next sprint. JSON inside `state_json` is queryable on Postgres (`->`, `->>`) and indexable when you need it.

## The bindings interface (swap point)

Two protocols. Every code path you write uses the protocols, never the concrete implementation.

```python
# app/db/bindings.py
from typing import Protocol, runtime_checkable
from sqlalchemy.orm import Session


@runtime_checkable
class DBBinding(Protocol):
    def session(self) -> Session: ...


@runtime_checkable
class BlobBinding(Protocol):
    def put(self, key: str, body: bytes, content_type: str) -> str: ...   # returns public_url or signed url
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def presign_put(self, key: str, content_type: str, expires_s: int = 3600) -> str: ...
```

## Routes (one place — works for all three paths)

```python
# app/routers/projects.py
import uuid
from fastapi import APIRouter, Depends
from app.deps import get_db, get_blobs
from app.db.schema import Project, Artifact

router = APIRouter(prefix="/projects", tags=["projects"])

_CONTENT_TYPES = {
    "geojson": "application/geo+json",
    "ifc": "model/ifc",
    "dotbim": "application/octet-stream",
    "png": "image/png",
    "json": "application/json",
}


@router.get("")
def list_projects(user_id: str, db = Depends(get_db)):
    with db.session() as s:
        rows = s.query(Project).filter_by(user_id=user_id, deleted_at=None).all()
        return [{"id": p.id, "name": p.name, "state": p.state_json} for p in rows]


@router.post("/{project_id}/artifacts/presign")
def presign(project_id: str, subtype: str, format: str,
            blobs = Depends(get_blobs)):
    key = f"projects/{project_id}/{subtype}/{uuid.uuid4().hex}.{format}"
    ct = _CONTENT_TYPES.get(format, "application/octet-stream")
    return {"key": key, "url": blobs.presign_put(key, ct)}
```

---

## Path A — Hackathon today (SQLite + local filesystem)

Zero external services. Runs anywhere Python runs. Perfect for the demo machine. Migrating off it later is one config change.

```python
# app/bindings/sqlite_local.py
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ENGINE = create_engine("sqlite:///./data/app.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=ENGINE, expire_on_commit=False)

class SqliteDB:
    def session(self): return SessionLocal()

class LocalBlobs:
    def __init__(self, root: Path = Path("./data/blobs")):
        self.root = root; root.mkdir(parents=True, exist_ok=True)
    def put(self, key, body, content_type):
        path = self.root / key; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body); return f"/blobs/{key}"
    def get(self, key): return (self.root / key).read_bytes()
    def delete(self, key): (self.root / key).unlink(missing_ok=True)
    def presign_put(self, key, content_type, expires_s=3600):
        # No presigning locally — frontend uploads through FastAPI directly.
        return f"/blobs/upload?key={key}"
```

Mount a `GET /blobs/{key}` route that streams from disk. Done.

**Persists across restarts. Loses data if Railway redeploys (use Railway Volumes if you want it to survive deploys).**

---

## Path B — Railway all-in (Postgres + Railway Buckets)

One platform, one bill, all S3-compatible. Railway Buckets is S3 over Tigris — `boto3` works.

**Provision in Railway dashboard:**
1. Project → New → **Database → PostgreSQL**. Railway injects `DATABASE_URL` into your service env.
2. Project → New → **Bucket**. Note the bucket name; Railway injects access keys.

**Bindings:**

```python
# app/bindings/railway.py
import os, boto3
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ENGINE = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
SessionLocal = sessionmaker(bind=ENGINE, expire_on_commit=False)

class PostgresDB:
    def session(self): return SessionLocal()

class RailwayBuckets:
    def __init__(self):
        self.bucket = os.environ["BUCKET"]
        self.s3 = boto3.client(
            "s3",
            endpoint_url=os.environ.get("ENDPOINT", "https://storage.railway.app"),
            aws_access_key_id=os.environ["ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["SECRET_ACCESS_KEY"],
            region_name=os.environ.get("REGION", "auto"),
        )
    def put(self, key, body, content_type):
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=body, ContentType=content_type)
        # Railway Buckets are private-only. Return a presigned GET URL for access.
        return self.s3.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=3600,
        )
    def get(self, key):
        return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
    def delete(self, key):
        self.s3.delete_object(Bucket=self.bucket, Key=key)
    def presign_put(self, key, content_type, expires_s=3600):
        return self.s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires_s,
        )
```

---

## Path C — Supabase all-in (Postgres + Storage + Auth)

Single signup, generous free tier (500 MB DB, 1 GB storage, 50K MAU), magic-link auth out of the box. Catch: free projects pause after **1 week of inactivity** — you manually unpause from the dashboard.

**Provision:** create a project at supabase.com → grab the Postgres connection string + the Storage S3 keys (Project Settings → Storage → S3 access).

**Bindings:**

```python
# app/bindings/supabase.py
import os, boto3
from botocore.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ENGINE = create_engine(os.environ["SUPABASE_DB_URL"], pool_pre_ping=True)
SessionLocal = sessionmaker(bind=ENGINE, expire_on_commit=False)

class SupabaseDB:
    def session(self): return SessionLocal()

class SupabaseStorage:
    def __init__(self):
        self.bucket = os.environ["SUPABASE_BUCKET"]
        ref = os.environ["SUPABASE_PROJECT_REF"]
        self.s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{ref}.storage.supabase.co/storage/v1/s3",
            aws_access_key_id=os.environ["SUPABASE_S3_KEY_ID"],
            aws_secret_access_key=os.environ["SUPABASE_S3_SECRET"],
            region_name=os.environ["SUPABASE_REGION"],  # copy from Project Settings → Storage → S3 access
            config=Config(s3={"addressing_style": "path"}),
        )
    # put / get / delete / presign_put: identical body to RailwayBuckets above.
```

**Auth — magic link in 10 lines:**

```python
# app/routers/auth.py
import os
from fastapi import APIRouter
from supabase import create_client

router = APIRouter(prefix="/auth", tags=["auth"])
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])

@router.post("/magic-link")
def magic_link(email: str):
    sb.auth.sign_in_with_otp({"email": email, "options": {
        "email_redirect_to": "https://my-app.lovable.app/callback"
    }})
    return {"sent": True}
```

The frontend hits `/callback?access_token=...`, hands the JWT to your FastAPI; verify it with Supabase's JWT secret (use `PyJWT` or `python-jose`; verification code is not in this recipe — implement it before going live with real users).

---

## Picking a path

| | A: SQLite | B: Railway | C: Supabase |
|---|---|---|---|
| DB | SQLite file | Postgres | Postgres |
| Blob | local fs | Buckets (S3) | Storage (S3) |
| Auth | none | bring your own | built-in magic-link |
| Data survives redeploy | needs Volume | yes | yes |
| Idle behavior | nothing | always-on | pauses after 1 week |

**Default for hackathon:** A for the first few hours (zero ops), then C if you need user accounts. Skip B unless you've already paid for Railway Hobby and want one bill.

---

## Adding users and a credit ledger

Same two-table shape, plus two more. Snippets in this section assume the standard FastAPI imports plus `import uuid` and `from app.db.schema_users import User, CreditLedger` already in scope.

```python
# app/db/schema_users.py
from datetime import datetime
from sqlalchemy import String, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.db.schema import Base, _uuid


class User(Base):
    __tablename__ = "users"
    id:         Mapped[str]      = mapped_column(String(32), primary_key=True, default=_uuid)
    email:      Mapped[str]      = mapped_column(String(255), unique=True, index=True)
    stripe_customer_id: Mapped[str|None] = mapped_column(String(64), nullable=True)
    credits:    Mapped[int]      = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CreditLedger(Base):
    __tablename__ = "credit_ledger"
    id:        Mapped[str]      = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id:   Mapped[str]      = mapped_column(String(32), index=True)
    delta:     Mapped[int]      = mapped_column(Integer)         # +50 (purchase) or -2 (sim run)
    reason:    Mapped[str]      = mapped_column(String(64))      # purchase | sim_run | refund
    ref:       Mapped[str|None] = mapped_column(String(64), nullable=True)  # stripe_session_id or artifact_id
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

Deduct on sim run — wrap the existing wrapper from [`python-fastapi-railway.md`](python-fastapi-railway.md):

```python
# app/services/billing.py
from sqlalchemy.exc import IntegrityError

def deduct_credits(db, user_id: str, amount: int, ref: str) -> bool:
    with db.session() as s:
        user = s.query(User).filter_by(id=user_id).with_for_update().one()
        if user.credits < amount:
            return False
        user.credits -= amount
        s.add(CreditLedger(user_id=user_id, delta=-amount, reason="sim_run", ref=ref))
        try:
            s.commit(); return True
        except IntegrityError:
            s.rollback(); return False
```

Route guard:

```python
@router.post("/sims/sun-hours")
def sun_hours(req: SunHoursRequest, user = Depends(current_user), db = Depends(get_db)):
    if not deduct_credits(db, user.id, amount=1, ref=f"sun-hours/{uuid.uuid4().hex}"):
        raise HTTPException(402, "Insufficient credits")
    return run_sun_hours(req.lat, req.lon, req.month)
```

## Stripe webhook stub

Add credits when a Checkout session completes. Use Stripe Checkout in test mode — works on Railway / Render / Supabase Edge alike.

```python
# app/routers/stripe_webhook.py
import os, stripe
from stripe import SignatureVerificationError
from fastapi import APIRouter, Request, HTTPException, Depends

router = APIRouter()
stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
WEBHOOK_SECRET = os.environ["STRIPE_WEBHOOK_SECRET"]

@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, WEBHOOK_SECRET)
    except SignatureVerificationError:
        raise HTTPException(400, "Bad signature")
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        credits = int(session["metadata"]["credits"])
        user_id = session["client_reference_id"]
        with db.session() as s:
            # Idempotency: Stripe retries webhooks on timeout. The ledger ref
            # (=session id) lets us no-op on duplicate deliveries.
            if s.query(CreditLedger).filter_by(reason="purchase", ref=session["id"]).first():
                return {"ok": True, "duplicate": True}
            user = s.query(User).filter_by(id=user_id).one()
            user.credits += credits
            s.add(CreditLedger(user_id=user_id, delta=credits, reason="purchase", ref=session["id"]))
            s.commit()
    return {"ok": True}
```

For stronger guarantees, add a unique constraint on `(reason, ref)` in the `CreditLedger` schema and catch `IntegrityError` instead of pre-querying — the DB then enforces idempotency under concurrent webhook deliveries.

When you create the Checkout Session, set `client_reference_id=user.id` and `metadata={"credits": "50"}`. Verify locally with `stripe listen --forward-to localhost:8000/webhooks/stripe`.

**EU VAT caveat:** the Stripe + credit-ledger pattern above ignores VAT/sales tax. The moment a European user buys credits, you owe VAT in their member state — register via [EU VAT OSS](https://vat-one-stop-shop.ec.europa.eu/index_en), layer [Stripe Tax](https://stripe.com/tax), or skip the problem entirely with Polar (next section).

## Billing shortcuts

Two alternatives to the raw Stripe + credit-ledger pattern, depending on what you want to skip.

### Polar.sh — Stripe + EU VAT handled for you

[Polar](https://polar.sh) sits on top of Stripe and acts as **Merchant of Record**: it handles EU VAT and US sales tax globally — you never register for VAT or remit anywhere. Webhooks follow [Standard Webhooks v1](https://www.standardwebhooks.com/) — don't roll the HMAC by hand (the spec has subtle base64 + multi-header rules that are easy to get wrong); use the official library.

```python
# app/routers/polar_webhook.py
# pip install standardwebhooks
import os, json
from fastapi import APIRouter, Request, HTTPException, Depends
from standardwebhooks import Webhook
from app.deps import get_db

router = APIRouter()
WEBHOOK = Webhook(os.environ["POLAR_WEBHOOK_SECRET"])


@router.post("/webhooks/polar")
async def polar_webhook(request: Request, db = Depends(get_db)):
    payload = await request.body()
    try:
        WEBHOOK.verify(payload, dict(request.headers))
    except Exception:
        raise HTTPException(400, "Bad signature")
    event = json.loads(payload)
    # NOTE: use `order.paid`, not `order.created` — `created` fires while the order
    # is still pending payment; `paid` fires after the charge clears.
    if event["type"] == "order.paid":
        meta = event["data"]["metadata"]
        credits = int(meta.get("credits", 0))
        user_id = meta["user_id"]
        with db.session() as s:
            # Idempotency: same pattern as the Stripe webhook (Polar also retries).
            if s.query(CreditLedger).filter_by(reason="purchase", ref=event["data"]["id"]).first():
                return {"ok": True, "duplicate": True}
            user = s.query(User).filter_by(id=user_id).one()
            user.credits += credits
            s.add(CreditLedger(user_id=user_id, delta=credits, reason="purchase", ref=event["data"]["id"]))
            s.commit()
    return {"ok": True}
```

When you create the Polar Checkout Session, set `metadata={"user_id": user.id, "credits": "50"}` so the webhook can find the user and credit amount. You also get a hosted customer portal (subscription management, invoices, cancel) for free — zero lines on your side.

### Stripe Meters — charge per sim, no credit ledger

If pay-as-you-go fits better than upfront credits (charged per sim run, billed monthly), [Stripe Billing Meters](https://docs.stripe.com/api/billing/meter-event/create) replaces the entire `credits` column + `CreditLedger` table + `deduct_credits()` race-condition guard. One-time setup in the Stripe dashboard creates a Meter, Product, metered Price, and per-customer subscription. Then in the sim route:

```python
import stripe
stripe.api_key = os.environ["STRIPE_SECRET_KEY"]

def report_sim_run(stripe_customer_id: str, event_name: str = "sim_run") -> None:
    stripe.billing.MeterEvent.create(
        event_name=event_name,
        payload={"stripe_customer_id": stripe_customer_id, "value": "1"},
    )

# Replace `deduct_credits(...)` in your /sims route with:
report_sim_run(user.stripe_customer_id)
```

Tradeoff: invoice-at-month-end UX instead of "you have 47 credits left." For hackathon demos the upfront-credit shape is usually clearer to the audience.

## Pitfalls

- **`state_json` mutation in place** — SQLAlchemy doesn't notice in-place dict edits. Reassign: `project.state_json = json.dumps({**old, "active": new_id})`. Or use a JSON column type with `MutableDict`.
- **`idempotency_key` protects against duplicate writes** — every artifact INSERT carries a unique `idempotency_key` per project (commonly the SHA-256 of canonical-JSON params). The DB enforces uniqueness via the `uq_artifacts_idempotency` index, so retries and parallel runs converge on a single row instead of producing duplicates.
- **No row locking under SQLite** — `with_for_update()` is a no-op. For the hackathon it doesn't matter; under Postgres it's real.
- **Railway Buckets are private-only** — the virtual-hosted URL is not publicly accessible. Return a presigned GET URL from `put()` (as shown in the binding above), or proxy through your FastAPI endpoint.
- **Path A on Railway loses data on redeploy** unless you attach a Railway Volume. Documented surprise.
- **Supabase pause** — set a calendar reminder. Or use a free uptime ping (e.g., GitHub Actions cron hitting `/health` weekly) to keep the project warm.
- **Stripe in browser** — never use Stripe **Secret Key** client-side. Checkout Session creation happens on the backend; the frontend redirects to the returned URL.
- **JSON in URLs** for boundary geometry — fine for small polygons; for big ones, upload as an artifact and reference by `artifact_id`.

## See also

- Backend the routes live in: [`python-fastapi-railway.md`](python-fastapi-railway.md)
- Frontend that consumes these routes: [`typescript-frontend-patterns.md`](typescript-frontend-patterns.md)
- AI-generated frontend with auth wired up: [`lovable-frontend.md`](lovable-frontend.md)
- Webhooks (Standard Webhooks v1 verification — same pattern as Stripe): [`../06-webhooks.md`](../06-webhooks.md)
