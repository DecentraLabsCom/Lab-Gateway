import asyncio

from session_ticket_transport import build_session_ticket_headers, post_session_ticket_request


class _Response:
    pass


class _AsyncClient:
    instances = []

    def __init__(self, *, timeout):
        self.timeout = timeout
        self.calls = []
        self.__class__.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, *, headers, json):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return _Response()


def test_build_session_ticket_headers_preserves_optional_credentials():
    assert build_session_ticket_headers(
        authorization="Bearer token",
        internal_token="internal-token",
    ) == {
        "Content-Type": "application/json",
        "Authorization": "Bearer token",
        "X-Access-Token": "internal-token",
    }
    assert build_session_ticket_headers(authorization=None, internal_token="") == {
        "Content-Type": "application/json",
    }


def test_post_session_ticket_request_uses_json_post_and_timeout(monkeypatch):
    _AsyncClient.instances.clear()
    monkeypatch.setattr("session_ticket_transport.httpx.AsyncClient", _AsyncClient)

    response = asyncio.run(
        post_session_ticket_request(
            "https://auth.example/ticket",
            payload={"labId": "42"},
            authorization="Bearer token",
            internal_token="internal-token",
        )
    )

    assert isinstance(response, _Response)
    client = _AsyncClient.instances[0]
    assert client.timeout == 10
    assert client.calls == [{
        "url": "https://auth.example/ticket",
        "headers": {
            "Content-Type": "application/json",
            "Authorization": "Bearer token",
            "X-Access-Token": "internal-token",
        },
        "json": {"labId": "42"},
    }]