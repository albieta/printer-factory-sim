"""Gemini API client for the turn engine.

Wraps Google Generative Language v1beta REST endpoints (``generateContent``
plus ``cachedContents``) so the engine can drive agents with Gemini models
instead of Claude. Designed for ``gemini-3.1-flash-lite`` free-tier limits:

  * 15 requests per minute (RPM)
  * 250,000 input tokens per minute (TPM) — rarely the binding constraint
  * 500 requests per day (RPD)

Why not the Google SDK
----------------------
``httpx`` is already a project dependency. Adding ``google-genai`` would pull
gRPC and dozens of transitive packages, all to call two REST endpoints.
The SDK also makes it harder to thread our own rate-limiter in front of
every outbound call.

Concurrency
-----------
A single ``GeminiClient`` instance is shared per engine subprocess via
``get_gemini_client()``. The internal rate limiter holds a ``threading.Lock``
so the parallel-agents mode (which fires three agents concurrently) cannot
exceed the bucket.

Caching
-------
Two layers, used opportunistically:

1. **Explicit caching** via ``cachedContents``: on first use we try to upload
   the skill file and reuse the returned cache name on every subsequent day.
   The free tier of ``gemini-3.1-flash-lite`` currently sets
   ``TotalCachedContentStorageTokensPerModelFreeTier=0`` so this 429s and is
   remembered as unavailable.
2. **Implicit caching**: Gemini 2.5+ and 3.x models automatically detect
   identical prompt prefixes (≥1024 tokens) and bill cache hits at 25%. We
   pass the static skill as ``systemInstruction`` on every call so the
   prefix stays identical across days, which lets implicit caching kick in
   without any explicit setup.

Either path is transparent to callers.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx


GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_DEFAULT_MODEL = "gemini-3.1-flash-lite"
GEMINI_REQUEST_TIMEOUT = 60.0
GEMINI_CACHE_TTL = "900s"  # 15 min — long enough to cover a full scenario run

# Free-tier limits for gemini-3.1-flash-lite as of 2026-05.
DEFAULT_RPM = 15
DEFAULT_RPD = 500
DEFAULT_TPM = 250_000

# Persist day-counter on disk so a process restart cannot reset RPD silently.
USAGE_FILE = Path("logs") / "gemini_usage.json"


# ── rate limiter ──────────────────────────────────────────────────────────────


class _RateLimiter:
    """Sliding-window limiter with persisted daily counter.

    Tracks three independent budgets (RPM, TPM, RPD). ``acquire`` blocks the
    caller until all three budgets allow the request, then reserves them. RPD
    is persisted to disk so the daily cap survives restarts.
    """

    def __init__(self, rpm: int = DEFAULT_RPM, tpm: int = DEFAULT_TPM, rpd: int = DEFAULT_RPD) -> None:
        self._rpm = rpm
        self._tpm = tpm
        self._rpd = rpd
        # (timestamp, tokens) entries within the last 60s.
        self._window: deque[tuple[float, int]] = deque()
        self._lock = threading.Lock()
        self._day_key, self._day_count = self._load_usage()

    @staticmethod
    def _today_key() -> str:
        # UTC day boundary — matches Google's accounting.
        return time.strftime("%Y-%m-%d", time.gmtime())

    def _load_usage(self) -> tuple[str, int]:
        try:
            data = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
            day = str(data.get("day", ""))
            count = int(data.get("count", 0))
            if day == self._today_key():
                return day, count
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        return self._today_key(), 0

    def _persist_usage(self) -> None:
        try:
            USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
            USAGE_FILE.write_text(
                json.dumps({"day": self._day_key, "count": self._day_count}),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _prune(self, now: float) -> tuple[int, int]:
        # Drop entries older than 60s. Returns (requests_in_window, tokens_in_window).
        cutoff = now - 60.0
        while self._window and self._window[0][0] < cutoff:
            self._window.popleft()
        req_count = len(self._window)
        tok_count = sum(t for _, t in self._window)
        return req_count, tok_count

    def acquire(self, estimated_tokens: int) -> None:
        """Block until the request fits all three budgets, then reserve them."""
        # Cap the estimate so a misbehaving caller cannot deadlock the limiter.
        estimated_tokens = min(max(0, estimated_tokens), self._tpm)

        while True:
            with self._lock:
                # Roll over the day counter if we crossed midnight UTC.
                today = self._today_key()
                if today != self._day_key:
                    self._day_key = today
                    self._day_count = 0
                    self._persist_usage()

                if self._day_count >= self._rpd:
                    raise RuntimeError(
                        f"Gemini daily request budget exhausted "
                        f"({self._day_count}/{self._rpd}). Try again after UTC midnight."
                    )

                now = time.monotonic()
                req_count, tok_count = self._prune(now)

                if req_count < self._rpm and tok_count + estimated_tokens <= self._tpm:
                    self._window.append((now, estimated_tokens))
                    self._day_count += 1
                    self._persist_usage()
                    return

                # Sleep until the oldest entry ages out (or 1s, whichever comes first).
                oldest_ts = self._window[0][0] if self._window else now
                wait = max(0.25, 60.0 - (now - oldest_ts) + 0.1)

            time.sleep(min(wait, 5.0))


# ── client ────────────────────────────────────────────────────────────────────


@dataclass
class _CacheEntry:
    name: str           # e.g. "cachedContents/abc123"
    created_at: float


class GeminiClient:
    """Thin wrapper around Gemini REST that respects free-tier limits and caches skills."""

    def __init__(
        self,
        api_key: str,
        model: str = GEMINI_DEFAULT_MODEL,
        rate_limiter: Optional[_RateLimiter] = None,
    ) -> None:
        if not api_key:
            raise ValueError("GOOGLE_API_KEY is required for Gemini agents")
        self._api_key = api_key
        self._model = model
        self._limiter = rate_limiter or _RateLimiter()
        # skill_path → cache entry. ``None`` means create failed; do not retry.
        self._skill_cache: dict[str, Optional[_CacheEntry]] = {}
        self._cache_lock = threading.Lock()

    @property
    def model(self) -> str:
        return self._model

    # ── public ──

    def generate(
        self,
        system_instruction: str,
        user_prompt: str,
        skill_path: Optional[str] = None,
        skill_text: Optional[str] = None,
    ) -> dict[str, Any]:
        """Run one generation. Returns ``{"text": str, "raw": dict, "usage": dict}``.

        When ``skill_path``/``skill_text`` are provided, the skill is uploaded
        as a cached content resource (once per process) and referenced by name
        on every subsequent call. The remaining ``system_instruction`` stays
        inline and should be small/per-day (e.g. role banner).
        """
        cache_name: Optional[str] = None
        if skill_path and skill_text:
            cache_name = self._ensure_cached_skill(skill_path, skill_text)

        # Rough token estimate: ~4 chars/token. The skill cost is excluded when
        # we're hitting a cache (cached tokens don't count against TPM).
        estimate_chars = len(user_prompt) + len(system_instruction)
        if cache_name is None and skill_text:
            estimate_chars += len(skill_text)
        estimated_tokens = max(256, estimate_chars // 4)

        body: dict[str, Any] = {
            "contents": [
                {"role": "user", "parts": [{"text": user_prompt}]},
            ],
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": 4096,
            },
        }

        if cache_name:
            body["cachedContent"] = cache_name
        else:
            # System instruction carries the skill text inline when we have no cache.
            combined_system = system_instruction
            if skill_text:
                combined_system = f"{system_instruction}\n\n{skill_text}".strip()
            if combined_system:
                body["systemInstruction"] = {"parts": [{"text": combined_system}]}

        self._limiter.acquire(estimated_tokens)

        url = f"{GEMINI_API_BASE}/models/{self._model}:generateContent"
        with httpx.Client(timeout=GEMINI_REQUEST_TIMEOUT) as client:
            resp = client.post(url, params={"key": self._api_key}, json=body)

        # 429 → likely a TPM/RPM race; back off once and retry.
        if resp.status_code == 429:
            time.sleep(5.0)
            self._limiter.acquire(estimated_tokens)
            with httpx.Client(timeout=GEMINI_REQUEST_TIMEOUT) as client:
                resp = client.post(url, params={"key": self._api_key}, json=body)

        resp.raise_for_status()
        data = resp.json()
        text = _extract_text(data)
        usage = data.get("usageMetadata", {})
        return {"text": text, "raw": data, "usage": usage}

    # ── internals ──

    def _ensure_cached_skill(self, skill_path: str, skill_text: str) -> Optional[str]:
        """Create or reuse a cachedContents resource for *skill_text*.

        Returns the cache name (``cachedContents/...``) or ``None`` if caching
        is unsupported / failed for this path (caller falls back to inline).
        """
        with self._cache_lock:
            existing = self._skill_cache.get(skill_path, "missing")
            if existing != "missing":
                # We've already decided for this path — either a cache name or None.
                return existing.name if isinstance(existing, _CacheEntry) else None

        # The cache create call also counts towards RPD, so go through the limiter.
        try:
            self._limiter.acquire(estimated_tokens=len(skill_text) // 4)
        except RuntimeError:
            with self._cache_lock:
                self._skill_cache[skill_path] = None
            return None

        body = {
            "model": f"models/{self._model}",
            "contents": [
                {"role": "user", "parts": [{"text": skill_text}]},
            ],
            "ttl": GEMINI_CACHE_TTL,
        }
        url = f"{GEMINI_API_BASE}/cachedContents"
        try:
            with httpx.Client(timeout=GEMINI_REQUEST_TIMEOUT) as client:
                resp = client.post(url, params={"key": self._api_key}, json=body)
            if resp.status_code >= 400:
                # Common failures: skill is below the model's minimum cacheable
                # size, or the free tier sets the cache-storage quota to 0
                # (current state for gemini-3.1-flash-lite). Either way, fall
                # back to inline systemInstruction and rely on Google's
                # automatic implicit caching for repeated prompt prefixes.
                with self._cache_lock:
                    self._skill_cache[skill_path] = None
                return None
            data = resp.json()
            name = str(data.get("name", ""))
            if not name:
                with self._cache_lock:
                    self._skill_cache[skill_path] = None
                return None
            entry = _CacheEntry(name=name, created_at=time.monotonic())
            with self._cache_lock:
                self._skill_cache[skill_path] = entry
            return name
        except httpx.HTTPError:
            with self._cache_lock:
                self._skill_cache[skill_path] = None
            return None


# ── helpers ──────────────────────────────────────────────────────────────────


_BASH_BLOCK = re.compile(r"```(?:bash|sh|shell)?\s*\n(.*?)```", re.DOTALL)


def _extract_text(payload: dict[str, Any]) -> str:
    """Concatenate text parts from the first candidate of a generateContent response."""
    candidates = payload.get("candidates", [])
    if not candidates:
        # Sometimes the API returns a top-level safety block with no candidate.
        if payload.get("promptFeedback"):
            return f"[blocked] {json.dumps(payload['promptFeedback'])}"
        return ""
    parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts if isinstance(p, dict))


def extract_bash_commands(text: str) -> list[str]:
    """Pull every shell command out of ```bash blocks in the agent's response.

    Lines that are blank or pure comments are dropped. Multiline backslash
    continuations are joined into a single command. ``&&``/``;`` chains are
    preserved verbatim — they execute as one shell invocation, which matches
    the "batch with &&" pattern used in the skill files.
    """
    commands: list[str] = []
    for block in _BASH_BLOCK.findall(text):
        # Join backslash continuations.
        joined = re.sub(r"\\\s*\n\s*", " ", block)
        for raw in joined.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            commands.append(line)
    return commands


# ── module-level singleton ────────────────────────────────────────────────────


_client_lock = threading.Lock()
_client: Optional[GeminiClient] = None


def get_gemini_client(model: str = GEMINI_DEFAULT_MODEL) -> GeminiClient:
    """Return a process-wide Gemini client, building it lazily on first call.

    Reads ``GOOGLE_API_KEY`` from the environment. Raises ``RuntimeError`` if
    the key is missing so callers can surface a clear message to the operator
    instead of a generic 401 from the Google API.
    """
    global _client
    with _client_lock:
        if _client is None or _client.model != model:
            api_key = os.environ.get("GOOGLE_API_KEY", "").strip()
            if not api_key:
                raise RuntimeError(
                    "GOOGLE_API_KEY is not set. Add it to .env at the repo root "
                    "or export it before launching the engine."
                )
            _client = GeminiClient(api_key=api_key, model=model)
        return _client


def is_gemini_model(model: str) -> bool:
    return model.lower().startswith("gemini")
