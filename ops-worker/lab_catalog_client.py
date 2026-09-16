"""Secure client for the provider lab catalog exposed by blockchain-services."""

from collections.abc import Callable, Mapping
from urllib.parse import urlsplit
from typing import Any, Dict, List


def _validate_catalog_url(url: str, *, allow_insecure: bool) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise ValueError("lab catalog URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError("lab catalog URL must not contain credentials")
    if parsed.scheme == "http" and not allow_insecure:
        raise ValueError("insecure lab catalog URL requires explicit opt-in")


def fetch_lab_catalog(
    url: str,
    token: str,
    token_header: str,
    *,
    allow_insecure: bool,
    http_get: Callable[..., Any],
    timeout: float,
) -> List[Dict[str, Any]]:
    """Fetch and minimally validate the backend lab catalog.

    The URL and credential are runtime configuration, never request input.  The
    function intentionally returns only dictionary entries with a non-empty
    ``labId``; the resolver performs the stricter relationship checks.
    """
    normalized_url = str(url or "").strip()
    normalized_token = str(token or "")
    normalized_header = str(token_header or "").strip()
    if not normalized_url:
        return []
    if not normalized_token:
        raise ValueError("lab catalog credential is not configured")
    if not normalized_header:
        raise ValueError("lab catalog credential header is not configured")
    _validate_catalog_url(normalized_url, allow_insecure=allow_insecure)

    response = http_get(
        normalized_url,
        headers={normalized_header: normalized_token},
        timeout=timeout,
        allow_redirects=False,
    )
    if int(getattr(response, "status_code", 0)) != 200:
        raise ValueError("lab catalog request failed")
    payload = response.json()
    rows = (
        payload
        if isinstance(payload, list)
        else payload.get("labs") if isinstance(payload, Mapping) else None
    )
    if not isinstance(rows, list):
        raise ValueError("lab catalog response is malformed")

    result: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        lab_id = str(row.get("labId") or "").strip()
        if lab_id:
            result.append(dict(row))
    return result


__all__ = ["fetch_lab_catalog"]
