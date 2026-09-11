from typing import Callable, Optional


def normalize_lab_id(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def get_claim_lab_id(
    claims: dict,
    *,
    normalizer: Callable[[object], Optional[str]] = normalize_lab_id,
) -> Optional[str]:
    return normalizer(claims.get("labId"))


def claim_reservation_key(claims: dict) -> str:
    return str(claims.get("reservationKey") or "").strip().lower()


def coerce_epoch_seconds(value) -> Optional[int]:
    """Best-effort conversion of JWT epoch-like values to integer seconds."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None