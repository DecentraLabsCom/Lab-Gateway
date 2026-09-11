from typing import Optional


def normalize_ticket_id(session_ticket: Optional[str]) -> Optional[str]:
    if not session_ticket:
        return None
    token = str(session_ticket).strip()
    if token.startswith("st_"):
        token = token[3:]
    return token[:10] if token else None