from typing import Any, Optional

import httpx


def build_session_ticket_headers(
    *,
    authorization: Optional[str],
    internal_token: str,
) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if authorization:
        headers["Authorization"] = authorization
    if internal_token:
        headers["X-Access-Token"] = internal_token
    return headers


async def post_session_ticket_request(
    url: str,
    *,
    payload: dict[str, Any],
    authorization: Optional[str],
    internal_token: str,
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=10) as client:
        return await client.post(
            url,
            headers=build_session_ticket_headers(
                authorization=authorization,
                internal_token=internal_token,
            ),
            json=payload,
        )