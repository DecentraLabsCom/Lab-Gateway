"""NETIO REST JSON driver for non-APC smart power strips."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol

import requests

from power.models import PowerCapabilities

from .base import PowerDriverError


class NetioJsonError(PowerDriverError):
    """Sanitized NETIO JSON error with a stable operational error code."""

    def __init__(self, error_code: str, message: str = "NETIO JSON operation failed") -> None:
        super().__init__(message)
        self.error_code = error_code


class NetioResponse(Protocol):
    status_code: int

    def json(self) -> Any:
        raise NotImplementedError


class NetioHttpClient(Protocol):
    def get(self, url: str, *, auth: Any, timeout: int, verify: bool) -> NetioResponse:
        raise NotImplementedError

    def post(
        self,
        url: str,
        *,
        json: Mapping[str, Any],
        auth: Any,
        timeout: int,
        verify: bool,
    ) -> NetioResponse:
        raise NotImplementedError


class _RequestsNetioClient:
    def get(self, url: str, *, auth: Any, timeout: int, verify: bool) -> NetioResponse:
        return requests.get(url, auth=auth, timeout=timeout, verify=verify)

    def post(
        self,
        url: str,
        *,
        json: Mapping[str, Any],
        auth: Any,
        timeout: int,
        verify: bool,
    ) -> NetioResponse:
        return requests.post(
            url,
            json=dict(json),
            auth=auth,
            timeout=timeout,
            verify=verify,
            headers={"Content-Type": "application/json"},
        )


def _error_code(exc: Exception) -> str:
    message = str(exc).lower()
    if "timeout" in message:
        return "TIMEOUT"
    if "connection" in message or "network" in message or "dns" in message:
        return "CONNECTION_FAILED"
    return "HTTP_REQUEST_FAILED"


def _output_id(value: Any) -> str:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise NetioJsonError("INVALID_RESPONSE", "NETIO returned an invalid output ID") from exc
    if parsed <= 0:
        raise NetioJsonError("INVALID_RESPONSE", "NETIO returned an invalid output ID")
    return str(parsed)


def _positive_int(value: Any, default: int, field_name: str) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise NetioJsonError("CONFIGURATION", f"NETIO {field_name} is invalid") from exc
    if parsed <= 0:
        raise NetioJsonError("CONFIGURATION", f"NETIO {field_name} must be positive")
    return parsed


class NetioJsonDriver:
    """Control NETIO outputs through the vendor's REST JSON API."""

    capabilities = PowerCapabilities(
        per_outlet_switching=True,
        read_back_state=True,
        power_cycle=True,
        per_outlet_metering=True,
        https_api=True,
    )

    def __init__(
        self,
        controller_id: str,
        host: str,
        *,
        port: int = 80,
        config: Optional[Mapping[str, Any]] = None,
        credentials: Optional[Mapping[str, Any]] = None,
        client: Optional[NetioHttpClient] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
    ) -> None:
        self.controller_id = str(controller_id)
        self.host = str(host or "").strip()
        if not self.host:
            raise NetioJsonError("CONFIGURATION", "NETIO host is required")
        try:
            self.port = int(port)
        except (TypeError, ValueError) as exc:
            raise NetioJsonError("CONFIGURATION", "NETIO port is invalid") from exc
        if not 1 <= self.port <= 65535:
            raise NetioJsonError("CONFIGURATION", "NETIO port is invalid")

        self.config = dict(config or {})
        self.path = str(self.config.get("path") or "/netio.json").strip()
        if not self.path.startswith("/") or "\n" in self.path or "\r" in self.path:
            raise NetioJsonError("CONFIGURATION", "NETIO API path is invalid")
        self.use_https = self._boolean(self.config.get("useHttps"), False)
        self.verify_tls = self._boolean(self.config.get("verifyTls"), True)
        self.timeout_seconds = _positive_int(
            self.config.get("timeoutSeconds"), 5, "timeoutSeconds"
        )
        self.retries = _positive_int(self.config.get("retries"), 1, "retries")
        self.credentials = dict(credentials or {})
        self.auth = self._basic_auth(self.credentials)
        self._client = client or _RequestsNetioClient()
        self._sleep = sleep_fn or (lambda _seconds: None)

    @staticmethod
    def _boolean(value: Any, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() not in {"false", "0", "no", "off"}
        return bool(value)

    @staticmethod
    def _basic_auth(credentials: Mapping[str, Any]):
        if not credentials:
            return None
        username = str(credentials.get("username") or "").strip()
        password = str(credentials.get("password") or "")
        if not username:
            raise NetioJsonError("CONFIGURATION", "NETIO credentials require a username")
        return (username, password)

    @property
    def _base_url(self) -> str:
        scheme = "https" if self.use_https else "http"
        return f"{scheme}://{self.host}:{self.port}{self.path}"

    def _request(self, method: str, payload: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        last_error: Optional[NetioJsonError] = None
        for attempt in range(self.retries + 1):
            try:
                if method == "GET":
                    response = self._client.get(
                        self._base_url,
                        auth=self.auth,
                        timeout=self.timeout_seconds,
                        verify=self.verify_tls,
                    )
                else:
                    response = self._client.post(
                        self._base_url,
                        json=payload or {},
                        auth=self.auth,
                        timeout=self.timeout_seconds,
                        verify=self.verify_tls,
                    )
                status = int(response.status_code)
                if status in {401, 403}:
                    code = "AUTHENTICATION_FAILED" if status == 401 else "JSON_API_FORBIDDEN"
                    raise NetioJsonError(code)
                if status != 200:
                    raise NetioJsonError(f"HTTP_{status}")
                body = response.json()
                if not isinstance(body, Mapping):
                    raise NetioJsonError("INVALID_RESPONSE", "NETIO returned an invalid JSON object")
                return dict(body)
            except NetioJsonError as exc:
                last_error = exc
                if exc.error_code in {"AUTHENTICATION_FAILED", "JSON_API_FORBIDDEN"}:
                    raise
            except (requests.RequestException, ValueError, TypeError) as exc:
                last_error = NetioJsonError(_error_code(exc))
            if attempt < self.retries:
                self._sleep(0)
        raise last_error or NetioJsonError("HTTP_REQUEST_FAILED")

    @staticmethod
    def _state(value: Any) -> str:
        if isinstance(value, bool):
            return "on" if value else "off"
        try:
            numeric = int(value)
        except (TypeError, ValueError) as exc:
            raise NetioJsonError("INVALID_RESPONSE", "NETIO returned an invalid output state") from exc
        if numeric == 1:
            return "on"
        if numeric == 0:
            return "off"
        raise NetioJsonError("INVALID_RESPONSE", "NETIO returned an unknown output state")

    @classmethod
    def _outputs(cls, body: Mapping[str, Any]) -> List[Mapping[str, Any]]:
        outputs = body.get("Outputs")
        if not isinstance(outputs, list):
            raise NetioJsonError("INVALID_RESPONSE", "NETIO response does not contain Outputs")
        result = []
        for output in outputs:
            if not isinstance(output, Mapping):
                raise NetioJsonError("INVALID_RESPONSE", "NETIO returned an invalid output")
            _output_id(output.get("ID"))
            result.append(output)
        return result

    @classmethod
    def _find_output(cls, body: Mapping[str, Any], outlet_id: str) -> Mapping[str, Any]:
        for output in cls._outputs(body):
            if _output_id(output.get("ID")) == outlet_id:
                return output
        raise NetioJsonError("OUTLET_NOT_FOUND", f"NETIO output '{outlet_id}' was not found")

    def discover(self) -> Dict[str, Any]:
        try:
            body = self._request("GET")
            agent = body.get("Agent") if isinstance(body.get("Agent"), Mapping) else {}
            outputs = self._outputs(body)
            return {
                "reachable": True,
                "driver": "netio-json",
                "controllerId": self.controller_id,
                "model": agent.get("Model"),
                "firmware": agent.get("Version"),
                "outletCount": len(outputs),
            }
        except NetioJsonError as exc:
            return {
                "reachable": False,
                "driver": "netio-json",
                "controllerId": self.controller_id,
                "errorCode": exc.error_code,
            }

    def list_outlets(self) -> List[Dict[str, Any]]:
        result = []
        for output in self._outputs(self._request("GET")):
            item = {
                "outlet": _output_id(output.get("ID")),
                "name": str(output.get("Name") or "").strip() or None,
                "state": self._state(output.get("State")),
            }
            if output.get("Load") is not None:
                item["load"] = output["Load"]
            result.append(item)
        return result

    def get_outlet_state(self, outlet_id: str) -> Dict[str, Any]:
        outlet = str(outlet_id).strip()
        if not outlet.isdigit() or int(outlet) <= 0:
            raise PowerDriverError("NETIO outlet must be a positive integer")
        output = self._find_output(self._request("GET"), outlet)
        return {"outlet": outlet, "state": self._state(output.get("State"))}

    def set_outlet_state(self, outlet_id: str, state: str, timeout_seconds: int = 20) -> Dict[str, Any]:
        del timeout_seconds
        outlet = str(outlet_id).strip()
        if not outlet.isdigit() or int(outlet) <= 0:
            raise PowerDriverError("NETIO outlet must be a positive integer")
        desired = str(state).strip().lower()
        if desired not in {"on", "off"}:
            raise PowerDriverError("NETIO outlet state must be on or off")
        body = self._request(
            "POST",
            {"Outputs": [{"ID": int(outlet), "Action": 1 if desired == "on" else 0}]},
        )
        output = self._find_output(body, outlet)
        return {"outlet": outlet, "state": self._state(output.get("State")), "success": True}

    def cycle_outlet(self, outlet_id: str, off_seconds: int = 10, timeout_seconds: int = 30) -> Dict[str, Any]:
        del timeout_seconds
        if int(off_seconds) <= 0:
            raise PowerDriverError("cycle off_seconds must be greater than zero")
        self.set_outlet_state(outlet_id, "off")
        self._sleep(off_seconds)
        return self.set_outlet_state(outlet_id, "on")
