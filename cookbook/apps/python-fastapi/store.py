"""In-memory run store: one run per set of inputs, old runs dropped.

Two rules keep it safe in a thread pool:
- `claim()` checks the cache and inserts the new run under ONE lock. Two equal
  requests at the same moment get the same run, so the run is billed once.
- Finished runs expire after `ttl_s`, and the store keeps at most `max_runs`.
  A done run holds its whole grid in memory, so the store must not grow forever.

For more than one worker process, put this in a database or Redis instead.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Run:
    id: str
    key: str  # hash of the inputs (the cache key)
    site: Any  # SiteRequest
    status: str = "queued"  # queued -> running -> done | failed
    jobs_done: int = 0
    jobs_total: int = 0
    error: str | None = None
    result: Any = None  # AreaResult when done
    png: bytes | None = None
    finished_at: float | None = None
    created_at: float = field(default_factory=time.monotonic)


class RunStore:
    def __init__(self, ttl_s: float = 3600, max_runs: int = 50) -> None:
        self.ttl_s, self.max_runs = ttl_s, max_runs
        self._lock = threading.Lock()
        self._runs: dict[str, Run] = {}  # run id -> run (insertion order = age)
        self._by_key: dict[str, str] = {}  # input hash -> run id

    def has_key(self, key: str) -> bool:
        with self._lock:
            return key in self._by_key

    def get(self, run_id: str) -> Run | None:
        with self._lock:
            return self._runs.get(run_id)

    def claim(self, key: str, site: Any) -> tuple[Run, bool]:
        """Return (run, is_new). Check and insert are atomic."""
        with self._lock:
            self._evict()
            if (run_id := self._by_key.get(key)) is not None:
                return self._runs[run_id], False
            run = Run(id=uuid.uuid4().hex[:12], key=key, site=site)
            self._runs[run.id], self._by_key[key] = run, run.id
            return run, True

    def finish(self, run: Run, status: str, error: str | None = None) -> None:
        with self._lock:
            run.status, run.error, run.finished_at = status, error, time.monotonic()
            if status == "failed":
                self._by_key.pop(run.key, None)  # let the user try again

    def _evict(self) -> None:
        """Drop expired finished runs, then the oldest finished runs over the cap."""
        now = time.monotonic()
        finished = [r for r in self._runs.values() if r.finished_at is not None]
        expired = {r.id for r in finished if now - r.finished_at > self.ttl_s}
        over = len(self._runs) - len(expired) - self.max_runs + 1  # +1: room for the new run
        if over > 0:
            rest = [r for r in finished if r.id not in expired]
            expired |= {r.id for r in rest[:over]}  # oldest first
        for run_id in expired:
            run = self._runs.pop(run_id)
            if self._by_key.get(run.key) == run_id:
                del self._by_key[run.key]
