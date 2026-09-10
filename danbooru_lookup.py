"""Optional, cached public Danbooru lookups for names absent from local data."""

import json
import logging
import threading
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_URL = "https://danbooru.donmai.us/tags.json"
USER_AGENT = "ComfyUI-Soter-Nodes/1.0 (+https://github.com/removeshort-prog/ComfyUI-Soter-Nodes)"
BATCH_SIZE = 100
REQUEST_TIMEOUT = 5
REQUEST_INTERVAL = 1.0
NAMED_TTL = 24 * 60 * 60
OTHER_TTL = 60 * 60
MAX_RESPONSE_BYTES = 1024 * 1024

_cache = {}
_lock = threading.Lock()
_next_request_at = 0.0
_warned = False
_logger = logging.getLogger(__name__)


def _normalize_name(name):
    return name.strip().lower().replace("\\(", "(").replace("\\)", ")").replace("_", " ")


def clear_lookup_cache():
    """Forget classifications while preserving the request rate limit."""
    with _lock:
        _cache.clear()


def _request_categories(names):
    canonical_names = [name.replace(" ", "_") for name in names]
    query = urlencode({
        "search[name_comma]": ",".join(canonical_names),
        "only": "name,category",
        "limit": BATCH_SIZE,
    })
    request = Request(f"{API_URL}?{query}", headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("Danbooru returned an oversized response")
    records = json.loads(raw)
    if not isinstance(records, list):
        raise ValueError("Danbooru did not return a tag list")

    requested = set(names)
    categories = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("name"), str):
            raise ValueError("Danbooru returned an invalid tag record")
        category = record.get("category")
        if type(category) is not int or category not in (0, 1, 3, 4, 5):
            raise ValueError("Danbooru returned an invalid tag category")
        name = _normalize_name(record["name"])
        if name not in requested:
            raise ValueError("Danbooru returned a name outside the requested batch")
        if name in categories and categories[name] != category:
            raise ValueError("Danbooru returned conflicting tag categories")
        categories[name] = category
    return {name: {3: "copyright", 4: "character"}.get(category) for name, category in categories.items()}


def lookup_named_categories(names):
    """Return known copyright/character names using normalized space-based keys.

    Successful non-name and absent results are cached for one hour. Network or
    malformed-response failures are retried on a future call, never cached as
    missing. Calls are serialized to respect one request per second globally.
    """
    global _next_request_at, _warned
    normalized = list(dict.fromkeys(
        _normalize_name(name) for name in names
        if isinstance(name, str) and name.strip() and "," not in name
    ))
    results = {}
    with _lock:
        pending = []
        now = time.monotonic()
        for name in normalized:
            cached = _cache.get(name)
            if cached is not None and cached[0] > now:
                if cached[1] is not None:
                    results[name] = cached[1]
            else:
                _cache.pop(name, None)
                pending.append(name)

        for offset in range(0, len(pending), BATCH_SIZE):
            batch = pending[offset:offset + BATCH_SIZE]
            wait = _next_request_at - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            _next_request_at = time.monotonic() + REQUEST_INTERVAL
            try:
                categories = _request_categories(batch)
            except Exception as exc:
                if not _warned:
                    _logger.warning("Danbooru name lookup failed; keeping existing tag classification: %s", exc)
                    _warned = True
                break

            expires_from = time.monotonic()
            for name in batch:
                category = categories.get(name)
                ttl = NAMED_TTL if category else OTHER_TTL
                _cache[name] = (expires_from + ttl, category)
                if category is not None:
                    results[name] = category
    return results
