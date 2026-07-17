from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from typing import Any, Callable, Optional
from urllib.parse import urlparse, urlunparse

import httpx
from fastapi import HTTPException


ModelMetadata = dict[str, Any]
logger = logging.getLogger("fmu-runner.backend")

_FMU_ACCESS_KEY_SEGMENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class BaseFmuBackend:
    mode = "unknown"
    supports_local_execution = False

    @staticmethod
    def validate_access_key(access_key: Any) -> str:
        access_key = str(access_key)
        segments = access_key.split("/")
        if (
            not access_key.lower().endswith(".fmu")
            or not segments
            or any(_FMU_ACCESS_KEY_SEGMENT_RE.fullmatch(segment) is None for segment in segments)
        ):
            raise HTTPException(status_code=400, detail="Token contains an invalid FMU file key")
        return access_key

    @classmethod
    def authorized_access_key(cls, claims: dict) -> str:
        access_key = claims.get("accessKey") or claims.get("fmuFileName")
        if not access_key:
            raise HTTPException(status_code=403, detail="Token has no authorised FMU file")
        return cls.validate_access_key(access_key)

    @classmethod
    def ensure_requested_access_key(cls, claims: dict, requested_fmu_filename: Optional[str]) -> str:
        access_key = cls.authorized_access_key(claims)
        if requested_fmu_filename and access_key != requested_fmu_filename:
            raise HTTPException(status_code=403, detail="Token is not authorised for requested FMU file")
        return cls.validate_access_key(requested_fmu_filename or access_key)

    @staticmethod
    def normalize_optional_string(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    async def health(self) -> dict:
        raise NotImplementedError

    async def get_authorized_model_metadata(self, *, claims: dict, requested_fmu_filename: Optional[str] = None) -> ModelMetadata:
        raise NotImplementedError

    async def list_authorized_fmu(self, *, claims: dict) -> dict:
        raise NotImplementedError


@dataclass
class LocalFmuBackend(BaseFmuBackend):
    health_loader: Callable[[], dict]
    model_metadata_loader: Callable[[str], ModelMetadata]
    list_loader: Callable[[str], dict]
    allow_execution: bool = True

    mode = "local"

    @property
    def supports_local_execution(self) -> bool:
        return self.allow_execution

    async def health(self) -> dict:
        payload = dict(self.health_loader())
        if not self.allow_execution:
            checks = dict(payload.get("checks") or {})
            checks["localExecutionEnabled"] = False
            payload["checks"] = checks
            payload["status"] = "DEGRADED"
            payload["backendMode"] = "local-disabled"
        return payload

    async def get_authorized_model_metadata(self, *, claims: dict, requested_fmu_filename: Optional[str] = None) -> ModelMetadata:
        fmu_filename = self.ensure_requested_access_key(claims, requested_fmu_filename)
        return self.model_metadata_loader(fmu_filename)

    async def list_authorized_fmu(self, *, claims: dict) -> dict:
        return self.list_loader(self.authorized_access_key(claims))


class StationFmuBackend(BaseFmuBackend):
    mode = "station"

    def __init__(
        self,
        *,
        base_url: str,
        internal_token: str = "",
        request_timeout: float = 10.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.internal_token = internal_token
        self.request_timeout = request_timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.internal_token:
            headers["X-Internal-Session-Token"] = self.internal_token
        return headers

    def _headers_for(
        self,
        *,
        accept: str = "application/json",
        authorization: Optional[str] = None,
    ) -> dict[str, str]:
        headers = {"Accept": accept}
        if self.internal_token:
            headers["X-Internal-Session-Token"] = self.internal_token
        if authorization:
            headers["Authorization"] = authorization
        return headers

    def _json_payload_for_station(
        self,
        *,
        claims: dict,
        access_key: str,
        lab_id: Optional[str],
        reservation_key: Optional[str],
        sim_id: Optional[str] = None,
        parameters: Optional[dict[str, Any]] = None,
        options: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "accessKey": access_key,
            "claims": claims,
            "parameters": parameters or {},
            "options": options or {},
        }
        if sim_id:
            payload["simId"] = sim_id
        if lab_id:
            payload["labId"] = lab_id
        if reservation_key:
            payload["reservationKey"] = reservation_key
        return payload

    @staticmethod
    def _response_error_detail(response: httpx.Response) -> str:
        # Do not relay Station's body: it may contain filesystem paths,
        # upstream URLs or framework diagnostics. Preserve only the status.
        return f"Station backend rejected request ({response.status_code})"

    def build_authorized_context(
        self,
        *,
        claims: dict,
        requested_fmu_filename: Optional[str] = None,
        requested_lab_id: Optional[str] = None,
        requested_reservation_key: Optional[str] = None,
    ) -> dict[str, Any]:
        access_key = self.ensure_requested_access_key(claims, requested_fmu_filename)
        claim_lab_id = self.normalize_optional_string(claims.get("labId"))
        requested_lab_id = self.normalize_optional_string(requested_lab_id)
        if claim_lab_id and requested_lab_id and claim_lab_id != requested_lab_id:
            raise HTTPException(status_code=403, detail="Token is not authorised for requested labId")

        claim_reservation_key = self.normalize_optional_string(claims.get("reservationKey"))
        requested_reservation_key = self.normalize_optional_string(requested_reservation_key)
        if requested_reservation_key and claim_reservation_key and requested_reservation_key.lower() != claim_reservation_key.lower():
            raise HTTPException(status_code=403, detail="Token is not authorised for requested reservationKey")

        return {
            "accessKey": access_key,
            "labId": requested_lab_id or claim_lab_id,
            "reservationKey": requested_reservation_key or claim_reservation_key,
            "claims": claims,
        }

    def build_internal_session_headers(self, *, authorization: Optional[str] = None) -> dict[str, str]:
        headers = {}
        if self.internal_token:
            headers["X-Internal-Session-Token"] = self.internal_token
        if authorization:
            headers["Authorization"] = authorization
        return headers

    def build_internal_session_message(
        self,
        *,
        message: dict[str, Any],
        claims: dict,
        requested_lab_id: Optional[str] = None,
        requested_reservation_key: Optional[str] = None,
    ) -> dict[str, Any]:
        context = self.build_authorized_context(
            claims=claims,
            requested_lab_id=requested_lab_id,
            requested_reservation_key=requested_reservation_key,
        )
        enriched = dict(message)
        gateway_context = {
            "mode": self.mode,
            "accessKey": context["accessKey"],
            "claims": context["claims"],
        }
        if context["labId"]:
            gateway_context["labId"] = context["labId"]
        if context["reservationKey"]:
            gateway_context["reservationKey"] = context["reservationKey"]
        if "gatewayContext" in enriched and isinstance(enriched["gatewayContext"], dict):
            merged = dict(enriched["gatewayContext"])
            merged.update(gateway_context)
            gateway_context = merged
        enriched["gatewayContext"] = gateway_context
        return enriched

    def station_session_ws_url(self) -> str:
        if not self.base_url:
            raise HTTPException(status_code=503, detail="Station backend is not configured")
        parsed = urlparse(self.base_url)
        if not parsed.scheme or not parsed.netloc:
            raise HTTPException(status_code=503, detail="Station backend URL is invalid")
        ws_scheme = "wss" if parsed.scheme == "https" else "ws"
        base_path = parsed.path.rstrip("/")
        path = f"{base_path}/internal/fmu/sessions" if base_path else "/internal/fmu/sessions"
        return urlunparse((ws_scheme, parsed.netloc, path, "", "", ""))

    async def _request_json(self, operation: str, *, access_key: Optional[str] = None) -> dict[str, Any]:
        if not self.base_url:
            raise HTTPException(status_code=503, detail="Station backend is not configured")

        key = ""
        if operation == "health":
            path = "/internal/health"
        elif operation in {"describe", "catalog"}:
            if access_key is None:
                raise HTTPException(status_code=400, detail="Token contains an invalid FMU file key")
            key = str(access_key)
            if not re.fullmatch(
                r"(?:[A-Za-z0-9][A-Za-z0-9._-]{0,127}/)*[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.fmu",
                key,
            ):
                raise HTTPException(status_code=400, detail="Token contains an invalid FMU file key")
            route = "describe" if operation == "describe" else "catalog"
            path = f"/internal/fmu/{route}"
        else:
            raise ValueError("Unsupported Station GET operation")

        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.request_timeout) as client:
                request_kwargs = {"headers": self._headers()}
                if operation in {"describe", "catalog"}:
                    request_kwargs["headers"]["X-FMU-Access-Key"] = key
                response = await client.get(path, **request_kwargs)
        except httpx.HTTPError as exc:
            logger.warning("Station backend GET failed: %s", exc)
            raise HTTPException(status_code=503, detail="Station backend unavailable") from exc

        if response.status_code >= 400:
            detail_text = response.text
            try:
                payload = response.json()
                if isinstance(payload, dict):
                    detail_text = payload.get("error") or payload.get("message") or detail_text
            except Exception:
                # A non-JSON error body is handled using the HTTP status instead.
                pass
            raise HTTPException(status_code=response.status_code, detail=detail_text)

        try:
            payload = response.json()
        except Exception as exc:
            logger.warning("Station backend returned invalid JSON for %s: %s", operation, exc)
            raise HTTPException(status_code=502, detail="Station backend returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise HTTPException(status_code=502, detail="Station backend returned invalid payload")
        return payload

    async def _post_json(
        self,
        operation: str,
        *,
        access_key: str,
        payload: dict[str, Any],
        authorization: Optional[str] = None,
    ) -> dict[str, Any]:
        if not self.base_url:
            raise HTTPException(status_code=503, detail="Station backend is not configured")

        key = str(access_key)
        if operation != "run" or not re.fullmatch(
            r"(?:[A-Za-z0-9][A-Za-z0-9._-]{0,127}/)*[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.fmu",
            key,
        ):
            raise HTTPException(status_code=400, detail="Token contains an invalid FMU file key")
        path = "/internal/fmu/simulations/run"
        station_payload = dict(payload)
        station_payload["accessKey"] = key
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.request_timeout) as client:
                response = await client.post(
                    path,
                    headers=self._headers_for(authorization=authorization),
                    json=station_payload,
                )
        except httpx.HTTPError as exc:
            logger.warning("Station backend POST failed: %s", exc)
            raise HTTPException(status_code=503, detail="Station backend unavailable") from exc

        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=self._response_error_detail(response))

        try:
            response_payload = response.json()
        except Exception as exc:
            logger.warning("Station backend returned invalid JSON for %s: %s", operation, exc)
            raise HTTPException(status_code=502, detail="Station backend returned invalid JSON") from exc
        if not isinstance(response_payload, dict):
            raise HTTPException(status_code=502, detail="Station backend returned invalid payload")
        return response_payload

    async def open_authorized_simulation_stream(
        self,
        *,
        claims: dict,
        request_payload: dict[str, Any],
        authorization: Optional[str] = None,
    ) -> tuple[httpx.AsyncClient, httpx.Response]:
        context = self.build_authorized_context(
            claims=claims,
            requested_lab_id=request_payload.get("labId"),
            requested_reservation_key=request_payload.get("reservationKey"),
        )
        access_key = context["accessKey"]
        payload = self._json_payload_for_station(
            claims=context["claims"],
            access_key=access_key,
            lab_id=context["labId"],
            reservation_key=context["reservationKey"],
            sim_id=request_payload.get("simId"),
            parameters=request_payload.get("parameters"),
            options=request_payload.get("options"),
        )
        key = str(access_key)
        if not re.fullmatch(
            r"(?:[A-Za-z0-9][A-Za-z0-9._-]{0,127}/)*[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.fmu",
            key,
        ):
            raise HTTPException(status_code=400, detail="Token contains an invalid FMU file key")
        path = "/internal/fmu/simulations/stream"
        client = httpx.AsyncClient(base_url=self.base_url, timeout=None)
        request = client.build_request(
            "POST",
            path,
            headers=self._headers_for(accept="application/x-ndjson", authorization=authorization),
            json=payload,
        )
        try:
            response = await client.send(request, stream=True)
        except httpx.HTTPError as exc:
            await client.aclose()
            logger.warning("Station backend stream failed: %s", exc)
            raise HTTPException(status_code=503, detail="Station backend unavailable") from exc

        if response.status_code >= 400:
            try:
                await response.aread()
            finally:
                await response.aclose()
                await client.aclose()
            raise HTTPException(status_code=response.status_code, detail=self._response_error_detail(response))
        return client, response

    async def run_authorized_simulation(
        self,
        *,
        claims: dict,
        request_payload: dict[str, Any],
        authorization: Optional[str] = None,
    ) -> dict[str, Any]:
        context = self.build_authorized_context(
            claims=claims,
            requested_lab_id=request_payload.get("labId"),
            requested_reservation_key=request_payload.get("reservationKey"),
        )
        access_key = context["accessKey"]
        payload = self._json_payload_for_station(
            claims=context["claims"],
            access_key=access_key,
            lab_id=context["labId"],
            reservation_key=context["reservationKey"],
            sim_id=request_payload.get("simId"),
            parameters=request_payload.get("parameters"),
            options=request_payload.get("options"),
        )
        return await self._post_json(
            "run",
            access_key=access_key,
            payload=payload,
            authorization=authorization,
        )

    @staticmethod
    def _normalize_variable(raw: dict[str, Any], fallback_reference: int) -> dict[str, Any]:
        value_reference = raw.get("valueReference")
        if value_reference is None:
            value_reference = fallback_reference
        entry = {
            "name": str(raw.get("name") or ""),
            "type": str(raw.get("type") or "Real"),
            "causality": str(raw.get("causality") or "local"),
            "variability": str(raw.get("variability") or "continuous"),
            "valueReference": int(value_reference),
        }
        if raw.get("unit") is not None:
            entry["unit"] = raw.get("unit")
        if raw.get("start") is not None:
            entry["start"] = raw.get("start")
        if raw.get("min") is not None:
            entry["min"] = raw.get("min")
        if raw.get("max") is not None:
            entry["max"] = raw.get("max")
        return entry

    def _normalize_model_metadata(self, payload: dict[str, Any]) -> ModelMetadata:
        raw_variables = payload.get("modelVariables")
        if raw_variables is None:
            raw_variables = payload.get("variables")
        if not isinstance(raw_variables, list):
            raise HTTPException(status_code=502, detail="Station backend response is missing model variables")

        supports_cs = payload.get("supportsCoSimulation")
        supports_me = payload.get("supportsModelExchange")
        simulation_kind = payload.get("simulationKind")
        simulation_type = payload.get("simulationType")

        if simulation_kind is None:
            if simulation_type == "CoSimulation":
                simulation_kind = "coSimulation"
            elif simulation_type == "ModelExchange":
                simulation_kind = "modelExchange"
            else:
                simulation_kind = "coSimulation" if supports_cs else ("modelExchange" if supports_me else "unknown")

        if simulation_type is None:
            simulation_type = "CoSimulation" if simulation_kind == "coSimulation" else (
                "ModelExchange" if simulation_kind == "modelExchange" else "Unknown"
            )

        normalized = {
            "modelName": str(payload.get("modelName") or "DecentraLabsProxy"),
            "guid": payload.get("guid"),
            "fmiVersion": str(payload.get("fmiVersion") or "2.0"),
            "simulationKind": str(simulation_kind),
            "simulationType": str(simulation_type),
            "supportsCoSimulation": bool(supports_cs if supports_cs is not None else simulation_kind == "coSimulation"),
            "supportsModelExchange": bool(supports_me if supports_me is not None else simulation_kind == "modelExchange"),
            "defaultStartTime": float(payload.get("defaultStartTime", 0.0)),
            "defaultStopTime": float(payload.get("defaultStopTime", 1.0)),
            "defaultStepSize": float(payload.get("defaultStepSize", 0.01)),
            "modelVariables": [],
        }

        guid = payload.get("guid")
        if guid:
            normalized["guid"] = str(guid)

        for index, variable in enumerate(raw_variables, start=1):
            if not isinstance(variable, dict):
                raise HTTPException(status_code=502, detail="Station backend returned an invalid model variable entry")
            normalized["modelVariables"].append(self._normalize_variable(variable, index))

        return normalized

    async def health(self) -> dict:
        checks = {
            "stationConfigured": bool(self.base_url),
            "stationHealth": False,
        }
        fmu_count = 0

        if not self.base_url:
            return {
                "status": "DEGRADED",
                "checks": checks,
                "fmuCount": fmu_count,
                "backendMode": self.mode,
            }

        try:
            payload = await self._request_json("health")
            checks["stationHealth"] = str(payload.get("status") or "").upper() == "UP"
            try:
                fmu_count = int(payload.get("fmuCount") or 0)
            except (TypeError, ValueError):
                fmu_count = 0
        except HTTPException:
            checks["stationHealth"] = False

        return {
            "status": "UP" if all(checks.values()) else "DEGRADED",
            "checks": checks,
            "fmuCount": fmu_count,
            "backendMode": self.mode,
        }

    async def get_authorized_model_metadata(self, *, claims: dict, requested_fmu_filename: Optional[str] = None) -> ModelMetadata:
        access_key = self.ensure_requested_access_key(claims, requested_fmu_filename)
        payload = await self._request_json("describe", access_key=access_key)
        return self._normalize_model_metadata(payload)

    async def list_authorized_fmu(self, *, claims: dict) -> dict:
        access_key = self.authorized_access_key(claims)
        try:
            payload = await self._request_json("catalog", access_key=access_key)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            metadata = await self.get_authorized_model_metadata(claims=claims, requested_fmu_filename=access_key)
            return {
                "fmus": [{
                    "filename": access_key,
                    "path": access_key,
                    "source": "station",
                    "simulationType": metadata["simulationType"],
                }]
            }

        fmus = payload.get("fmus")
        if isinstance(fmus, list):
            normalized_fmus = []
            for entry in fmus:
                if not isinstance(entry, dict):
                    continue
                normalized = dict(entry)
                normalized.setdefault("source", "station")
                normalized_fmus.append(normalized)
            return {"fmus": normalized_fmus}

        return {
            "fmus": [{
                "filename": access_key,
                "path": access_key,
                "source": "station",
            }]
        }
