from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from typing import Any

_CTX: ssl.SSLContext | None = None
_CTX_READY = False


def _ssl_context() -> ssl.SSLContext:
    global _CTX, _CTX_READY
    if _CTX_READY and _CTX is not None:
        return _CTX
    ctx = ssl.create_default_context()
    try:
        urllib.request.urlopen(
            "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
            timeout=5,
            context=ctx,
        )
    except Exception:
        ctx = ssl._create_unverified_context()
    _CTX = ctx
    _CTX_READY = True
    return ctx


def get_json(url: str, timeout: int = 30) -> Any:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "nba-ats-model/0.1 (+personal research)"},
    )
    try:
        with urllib.request.urlopen(
            request, timeout=timeout, context=_ssl_context()
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {body[:300]}") from exc
