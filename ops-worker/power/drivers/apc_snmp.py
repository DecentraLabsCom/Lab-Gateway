"""APC PowerNet SNMP driver.

The driver keeps the PowerNet OIDs in explicit profiles so the upper power
policy layer remains independent from APC model names.  The network client is
injectable for deterministic tests and for future SNMP client replacements.
"""

from __future__ import annotations

import asyncio
import importlib
import threading
from typing import Any, Dict, Iterable, List, Mapping, Optional, Protocol, Tuple

from power.models import PowerCapabilities

from .base import PowerDriverError


APC_LEGACY_OIDS = {
    "model": "1.3.6.1.4.1.318.1.1.4.1.4.0",
    "firmware": "1.3.6.1.4.1.318.1.1.4.1.2.0",
    "outlet_count": "1.3.6.1.4.1.318.1.1.4.4.1.0",
    "state": "1.3.6.1.4.1.318.1.1.4.4.2.1.3",
    "name": "1.3.6.1.4.1.318.1.1.4.4.2.1.4",
    "command": "1.3.6.1.4.1.318.1.1.4.4.2.1.3",
}

APC_RPDU2_OIDS = {
    "model": "1.3.6.1.4.1.318.1.1.26.2.1.8",
    "firmware": "1.3.6.1.4.1.318.1.1.26.2.1.6",
    "index": "1.3.6.1.4.1.318.1.1.26.9.2.3.1.1",
    "module": "1.3.6.1.4.1.318.1.1.26.9.2.3.1.2",
    "name": "1.3.6.1.4.1.318.1.1.26.9.2.3.1.3",
    "number": "1.3.6.1.4.1.318.1.1.26.9.2.3.1.4",
    "state": "1.3.6.1.4.1.318.1.1.26.9.2.3.1.5",
    "command": "1.3.6.1.4.1.318.1.1.26.9.2.4.1.5",
}

SYS_DESCR_OID = "1.3.6.1.2.1.1.1.0"


class SnmpClient(Protocol):
    def get(self, oid: str) -> Any:
        raise NotImplementedError

    def set(self, oid: str, value: int) -> Any:
        raise NotImplementedError

    def walk(self, oid: str) -> Iterable[Tuple[str, Any]]:
        raise NotImplementedError


class ApcSnmpError(PowerDriverError):
    """Sanitized APC SNMP error with a stable operational error code."""

    def __init__(self, error_code: str, message: str = "APC SNMP operation failed") -> None:
        super().__init__(message)
        self.error_code = error_code


def _text(value: Any) -> str:
    if hasattr(value, "prettyPrint"):
        value = value.prettyPrint()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    return str(value).strip()


def _int(value: Any, field_name: str) -> int:
    try:
        return int(_text(value))
    except (TypeError, ValueError) as exc:
        raise ApcSnmpError("INVALID_RESPONSE", f"APC SNMP returned an invalid {field_name}") from exc


def _oid(base: str, suffix: Any) -> str:
    return f"{base.rstrip('.')}.{str(suffix).strip('.')}"


def _row_suffix(base: str, row_oid: Any) -> str:
    prefix = base.rstrip(".") + "."
    row = _text(row_oid).lstrip(".")
    if not row.startswith(prefix):
        raise ApcSnmpError("INVALID_RESPONSE", "APC SNMP returned an invalid table row")
    return row[len(prefix):]


def _error_code(exc: Exception) -> str:
    message = str(exc).lower()
    if "timeout" in message or "no snmp response" in message:
        return "TIMEOUT"
    if "auth" in message or "authorization" in message or "community" in message:
        return "AUTHENTICATION_FAILED"
    if "no such" in message or "unknown object" in message or "oid" in message:
        return "OID_UNSUPPORTED"
    return "SNMP_REQUEST_FAILED"


class ApcPowerNetSnmpDriver:
    """Control legacy and rPDU2 APC switched outlets over SNMP."""

    capabilities = PowerCapabilities(
        per_outlet_switching=True,
        read_back_state=True,
        power_cycle=True,
        snmp_v1=True,
        snmp_v2c=True,
        snmp_v3=True,
    )

    def __init__(
        self,
        controller_id: str,
        host: str,
        *,
        port: int = 161,
        config: Optional[Mapping[str, Any]] = None,
        credentials: Optional[Mapping[str, Any]] = None,
        client: Optional[SnmpClient] = None,
    ) -> None:
        self.controller_id = str(controller_id)
        self.host = str(host or "").strip()
        if not self.host:
            raise ApcSnmpError("CONFIGURATION", "APC SNMP host is required")
        try:
            self.port = int(port)
        except (TypeError, ValueError) as exc:
            raise ApcSnmpError("CONFIGURATION", "APC SNMP port is invalid") from exc
        if not 1 <= self.port <= 65535:
            raise ApcSnmpError("CONFIGURATION", "APC SNMP port is invalid")

        self.config = dict(config or {})
        self.credentials = dict(credentials or {})
        self.version = str(
            self.credentials.get("version")
            or self.config.get("snmpVersion")
            or ""
        ).strip().lower()
        for key in ("securityName", "authProtocol", "privProtocol", "contextName"):
            if key not in self.credentials and self.config.get(key) is not None:
                self.credentials[key] = self.config[key]
        self._validate_credentials()
        self.credentials.setdefault("version", self.version)

        profile = str(self.config.get("profile") or "auto").strip().lower()
        if profile not in {"auto", "legacy", "rpdu2"}:
            raise ApcSnmpError("CONFIGURATION", "APC SNMP profile is invalid")
        self._configured_profile = profile
        self._selected_profile: Optional[str] = None if profile == "auto" else profile
        self._client = client or _PySnmpClient(
            self.host,
            self.port,
            self.credentials,
            timeout_seconds=self._positive_int(self.config.get("timeoutSeconds"), 2),
            retries=self._positive_int(self.config.get("retries"), 1),
        )

    @staticmethod
    def _positive_int(value: Any, default: int) -> int:
        if value is None:
            return default
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ApcSnmpError("CONFIGURATION", "APC SNMP numeric option is invalid") from exc
        if parsed <= 0:
            raise ApcSnmpError("CONFIGURATION", "APC SNMP numeric option must be positive")
        return parsed

    def _validate_credentials(self) -> None:
        if self.version not in {"v1", "v2c", "v3"}:
            raise ApcSnmpError("CONFIGURATION", "SNMP credentials must specify v1, v2c or v3")
        if self.version in {"v1", "v2c"}:
            if not str(self.credentials.get("community") or "").strip():
                raise ApcSnmpError("CONFIGURATION", "SNMP credentials require a community")
            return
        if not str(self.credentials.get("username") or self.credentials.get("securityName") or "").strip():
            raise ApcSnmpError("CONFIGURATION", "SNMP credentials require a username")

    def _call(self, method: str, *args: Any) -> Any:
        try:
            return getattr(self._client, method)(*args)
        except ApcSnmpError:
            raise
        except PowerDriverError:
            raise
        except Exception as exc:  # pragma: no cover - real client boundary
            raise ApcSnmpError(_error_code(exc)) from exc

    def _get(self, oid: str) -> Any:
        return self._call("get", oid)

    def _optional_get(self, oid: str) -> Optional[Any]:
        try:
            return self._get(oid)
        except PowerDriverError:
            return None

    def _walk(self, oid: str) -> List[Tuple[str, Any]]:
        rows = self._call("walk", oid)
        return [(str(row_oid), value) for row_oid, value in rows]

    def _profile(self) -> str:
        if self._selected_profile:
            return self._selected_profile
        count = 0
        try:
            count = _int(self._get(APC_LEGACY_OIDS["outlet_count"]), "outlet count")
            if count > 0:
                self._selected_profile = "legacy"
                return "legacy"
        except PowerDriverError:
            count = 0
        try:
            rows = self._walk(APC_RPDU2_OIDS["index"])
        except PowerDriverError as exc:
            raise ApcSnmpError("OID_UNSUPPORTED") from exc
        if not rows:
            raise ApcSnmpError("OID_UNSUPPORTED")
        self._selected_profile = "rpdu2"
        return "rpdu2"

    def _profile_oids(self) -> Mapping[str, str]:
        return APC_LEGACY_OIDS if self._profile() == "legacy" else APC_RPDU2_OIDS

    def _identity(self, profile: str) -> Tuple[Optional[str], Optional[str]]:
        oids = APC_LEGACY_OIDS if profile == "legacy" else APC_RPDU2_OIDS
        suffix = "" if profile == "legacy" else str(self.config.get("moduleIndex") or "1")
        model = self._optional_get(_oid(oids["model"], suffix) if suffix else oids["model"])
        firmware = self._optional_get(_oid(oids["firmware"], suffix) if suffix else oids["firmware"])
        if model is None and firmware is None:
            description = self._optional_get(SYS_DESCR_OID)
            model = _text(description) if description is not None else None
        return (
            _text(model) if model is not None else None,
            _text(firmware) if firmware is not None else None,
        )

    def discover(self) -> Dict[str, Any]:
        try:
            profile = self._profile()
            model, firmware = self._identity(profile)
            outlet_count = len(self._outlet_rows()) if profile == "rpdu2" else _int(
                self._get(APC_LEGACY_OIDS["outlet_count"]), "outlet count"
            )
            result: Dict[str, Any] = {
                "reachable": True,
                "driver": "apc-powernet-snmp",
                "controllerId": self.controller_id,
                "profile": profile,
                "model": model,
                "firmware": firmware,
                "outletCount": outlet_count,
            }
            return result
        except PowerDriverError as exc:
            return {
                "reachable": False,
                "driver": "apc-powernet-snmp",
                "controllerId": self.controller_id,
                "profile": self._selected_profile or self._configured_profile,
                "errorCode": getattr(exc, "error_code", "SNMP_REQUEST_FAILED"),
            }

    def _state(self, value: Any, profile: str) -> str:
        numeric = _int(value, "outlet state")
        if profile == "legacy":
            states = {1: "on", 2: "off"}
        else:
            states = {1: "off", 2: "on"}
        if numeric not in states:
            raise ApcSnmpError("UNKNOWN_STATE", "APC SNMP returned an unknown outlet state")
        return states[numeric]

    def _outlet_rows(self) -> List[Dict[str, Any]]:
        profile = self._profile()
        if profile == "legacy":
            count = _int(self._get(APC_LEGACY_OIDS["outlet_count"]), "outlet count")
            if count <= 0 or count > 512:
                raise ApcSnmpError("INVALID_RESPONSE", "APC SNMP returned an invalid outlet count")
            rows = []
            for number in range(1, count + 1):
                suffix = str(number)
                name = self._optional_get(_oid(APC_LEGACY_OIDS["name"], suffix))
                state = self._state(self._get(_oid(APC_LEGACY_OIDS["state"], suffix)), profile)
                rows.append({
                    "outlet": suffix,
                    "name": _text(name) if name is not None else None,
                    "state": state,
                })
            return rows

        index_rows = self._walk(APC_RPDU2_OIDS["index"])
        names = self._table_values(APC_RPDU2_OIDS["name"])
        numbers = self._table_values(APC_RPDU2_OIDS["number"])
        states = self._table_values(APC_RPDU2_OIDS["state"])
        rows = []
        for row_oid, _ in index_rows:
            index = _row_suffix(APC_RPDU2_OIDS["index"], row_oid)
            if index not in states:
                raise ApcSnmpError("INVALID_RESPONSE", "APC SNMP outlet state is missing")
            outlet = _text(numbers.get(index, index))
            rows.append({
                "outlet": outlet,
                "name": _text(names[index]) if index in names else None,
                "state": self._state(states[index], profile),
                "index": index,
            })
        return sorted(rows, key=lambda row: (int(row["outlet"]) if str(row["outlet"]).isdigit() else 0, row["outlet"]))

    def _table_values(self, base: str) -> Dict[str, Any]:
        return {
            _row_suffix(base, row_oid): value
            for row_oid, value in self._walk(base)
        }

    def list_outlets(self) -> List[Dict[str, Any]]:
        return [
            {key: value for key, value in row.items() if key != "index"}
            for row in self._outlet_rows()
        ]

    def get_outlet_state(self, outlet_id: str) -> Dict[str, Any]:
        outlet = str(outlet_id).strip()
        if not outlet or not outlet.isdigit() or int(outlet) <= 0:
            raise PowerDriverError("APC outlet must be a positive integer")
        profile = self._profile()
        oids = self._profile_oids()
        state = self._state(self._get(_oid(oids["state"], outlet)), profile)
        return {"outlet": outlet, "state": state}

    def set_outlet_state(self, outlet_id: str, state: str, timeout_seconds: int = 20) -> Dict[str, Any]:
        del timeout_seconds
        desired = str(state).strip().lower()
        if desired not in {"on", "off"}:
            raise PowerDriverError("APC outlet state must be on or off")
        outlet = str(outlet_id).strip()
        if not outlet.isdigit() or int(outlet) <= 0:
            raise PowerDriverError("APC outlet must be a positive integer")
        command = 1 if desired == "on" else 2
        self._call("set", _oid(self._profile_oids()["command"], outlet), command)
        return {"outlet": outlet, "state": desired, "success": True}

    def cycle_outlet(self, outlet_id: str, off_seconds: int = 10, timeout_seconds: int = 30) -> Dict[str, Any]:
        del timeout_seconds
        if int(off_seconds) <= 0:
            raise PowerDriverError("cycle off_seconds must be greater than zero")
        outlet = str(outlet_id).strip()
        if not outlet.isdigit() or int(outlet) <= 0:
            raise PowerDriverError("APC outlet must be a positive integer")
        self._profile()
        self._call("set", _oid(self._profile_oids()["command"], outlet), 3)
        return {"outlet": outlet, "state": "on", "success": True}


class _PySnmpClient:
    """Synchronous adapter around the supported PySNMP asyncio API."""

    def __init__(
        self,
        host: str,
        port: int,
        credentials: Mapping[str, Any],
        *,
        timeout_seconds: int,
        retries: int,
    ) -> None:
        self.host = host
        self.port = port
        self.credentials = dict(credentials)
        self.timeout_seconds = timeout_seconds
        self.retries = retries

    def _run(self, coroutine):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)

        result = []
        error = []

        def runner():
            try:
                result.append(asyncio.run(coroutine))
            except Exception as exc:  # pragma: no cover - only active loop edge
                error.append(exc)

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join()
        if error:
            raise error[0]
        return result[0]

    def _auth(self, module):
        version = str(self.credentials.get("version") or "").lower()
        if version == "v1":
            return module.CommunityData(str(self.credentials["community"]), mpModel=0)
        if version == "v2c":
            return module.CommunityData(str(self.credentials["community"]), mpModel=1)

        auth_protocols = {
            "NONE": module.usmNoAuthProtocol,
            "MD5": module.usmHMACMD5AuthProtocol,
            "SHA": module.usmHMACSHAAuthProtocol,
            "SHA224": module.usmHMAC128SHA224AuthProtocol,
            "SHA256": module.usmHMAC192SHA256AuthProtocol,
            "SHA384": module.usmHMAC256SHA384AuthProtocol,
            "SHA512": module.usmHMAC384SHA512AuthProtocol,
        }
        priv_protocols = {
            "NONE": module.usmNoPrivProtocol,
            "DES": module.usmDESPrivProtocol,
            "AES": module.usmAesCfb128Protocol,
            "AES128": module.usmAesCfb128Protocol,
        }
        auth_name = str(self.credentials.get("authProtocol") or "NONE").upper()
        priv_name = str(self.credentials.get("privProtocol") or "NONE").upper()
        try:
            return module.UsmUserData(
                str(self.credentials.get("username") or self.credentials.get("securityName")),
                authKey=self.credentials.get("authPassword") or self.credentials.get("authKey"),
                privKey=self.credentials.get("privPassword") or self.credentials.get("privKey"),
                authProtocol=auth_protocols[auth_name],
                privProtocol=priv_protocols[priv_name],
            )
        except KeyError as exc:
            raise ApcSnmpError("CONFIGURATION", "unsupported SNMPv3 security protocol") from exc

    async def _request(self, operation: str, oid: str, value: Optional[int] = None):
        try:
            module = importlib.import_module("pysnmp.hlapi.v3arch.asyncio")
        except ImportError as exc:  # pragma: no cover - dependency is installed in image
            raise ApcSnmpError("DEPENDENCY_MISSING", "PySNMP is not installed") from exc
        engine = module.SnmpEngine()
        try:
            target = await module.UdpTransportTarget.create(
                (self.host, self.port),
                timeout=self.timeout_seconds,
                retries=self.retries,
            )
            if operation == "set":
                request = module.ObjectType(module.ObjectIdentity(oid), module.Integer(value))
            else:
                request = module.ObjectType(module.ObjectIdentity(oid))
            command = module.get_cmd if operation == "get" else module.set_cmd
            error_indication, error_status, error_index, var_binds = await command(
                engine,
                self._auth(module),
                target,
                module.ContextData(),
                request,
            )
            if error_indication or error_status:
                detail = str(error_indication or error_status)
                raise ApcSnmpError(_error_code(Exception(detail))) from None
            if not var_binds:
                raise ApcSnmpError("INVALID_RESPONSE")
            return var_binds[0][1]
        finally:
            engine.close_dispatcher()

    async def _walk_async(self, oid: str):
        try:
            module = importlib.import_module("pysnmp.hlapi.v3arch.asyncio")
        except ImportError as exc:  # pragma: no cover - dependency is installed in image
            raise ApcSnmpError("DEPENDENCY_MISSING", "PySNMP is not installed") from exc
        engine = module.SnmpEngine()
        rows = []
        try:
            target = await module.UdpTransportTarget.create(
                (self.host, self.port),
                timeout=self.timeout_seconds,
                retries=self.retries,
            )
            async for error_indication, error_status, error_index, var_binds in module.walk_cmd(
                engine,
                self._auth(module),
                target,
                module.ContextData(),
                module.ObjectType(module.ObjectIdentity(oid)),
            ):
                if error_indication or error_status:
                    detail = str(error_indication or error_status)
                    raise ApcSnmpError(_error_code(Exception(detail))) from None
                rows.append((str(var_binds[0][0]), var_binds[0][1]))
            return rows
        finally:
            engine.close_dispatcher()

    def get(self, oid: str) -> Any:
        return self._run(self._request("get", oid))

    def set(self, oid: str, value: int) -> Any:
        return self._run(self._request("set", oid, value))

    def walk(self, oid: str) -> Iterable[Tuple[str, Any]]:
        return self._run(self._walk_async(oid))
