import pytest

from lab_catalog_client import fetch_lab_catalog


class _Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_fetch_lab_catalog_sends_only_configured_auth_header():
    calls = []
    payload = {"labs": [{"labId": "lab-1", "accessKey": "guac:id:5"}]}

    result = fetch_lab_catalog(
        "https://blockchain.example/lab-admin/labs",
        "catalog-token",
        "X-Lab-Manager-Token",
        allow_insecure=False,
        http_get=lambda *args, **kwargs: calls.append((args, kwargs)) or _Response(payload=payload),
        timeout=3,
    )

    assert result == payload["labs"]
    assert calls == [(
        ("https://blockchain.example/lab-admin/labs",),
        {
            "headers": {"X-Lab-Manager-Token": "catalog-token"},
            "timeout": 3,
            "allow_redirects": False,
        },
    )]


def test_fetch_lab_catalog_rejects_insecure_url_without_explicit_opt_in():
    with pytest.raises(ValueError):
        fetch_lab_catalog(
            "http://blockchain.example/lab-admin/labs",
            "token",
            "X-Lab-Manager-Token",
            allow_insecure=False,
            http_get=lambda *_args, **_kwargs: _Response(payload={"labs": []}),
            timeout=3,
        )


def test_fetch_lab_catalog_fails_closed_for_http_errors_and_malformed_payload():
    for response in (_Response(status_code=503, payload={"labs": []}), _Response(payload={"items": []})):
        with pytest.raises(ValueError):
            fetch_lab_catalog(
                "http://blockchain.example/lab-admin/labs",
                "token",
                "X-Lab-Manager-Token",
                allow_insecure=True,
                http_get=lambda *_args, response=response, **_kwargs: response,
                timeout=3,
            )
