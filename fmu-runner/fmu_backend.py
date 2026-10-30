from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import logging
import math
import re
from typing import Any, Callable, Optional
from urllib.parse import urlparse, urlunparse

import httpx
from fastapi import HTTPException
from fmi_ls_struct import normalize_fmi_ls_struct


ModelMetadata = dict[str, Any]
logger = logging.getLogger("fmu-runner.backend")

_FMU_ACCESS_KEY_SEGMENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_SIMULATION_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
_SAFE_SIMULATION_ERRORS = {
    "ASYNC_EXECUTION_REQUIRES_PROCESS_ISOLATION",
    "BATCH_SIZE_LIMIT_EXCEEDED",
    "BATCH_STEP_LIMIT_EXCEEDED",
    "FMU_COSIMULATION_REQUIRED",
    "FMU_ARCHIVE_SIZE_LIMIT_EXCEEDED",
    "FMU_SNAPSHOT_HASH_MISMATCH",
    "FMU_EXECUTION_TIMEOUT",
    "FMU_PROCESS_ISOLATION_REQUIRED",
    "FMU_NOT_COMPATIBLE",
    "FMU_NOT_FOUND",
    "EXECUTION_AUTHORIZATION_EXPIRED",
    "EXECUTION_AUTHORIZATION_EXPIRY_REQUIRED",
    "INVALID_EXECUTION_AUTHORIZATION_EXPIRY",
    "INVALID_RESERVATION_END",
    "INVALID_FMU_EXECUTION_POLICY",
    "RESERVATION_NOT_ACTIVE",
    "INVALID_SIMULATION_ID",
    "INVALID_SIMULATION_OPTIONS",
    "INVALID_SIMULATION_PARAMETERS",
    "INVALID_SIMULATION_REQUEST",
    "RESERVATION_DAILY_SCENARIO_LIMIT",
    "RESULT_SIZE_LIMIT_EXCEEDED",
    "RESERVATION_ENDED",
    "SIMULATION_NOT_FINISHED",
    "SIMULATION_NOT_FOUND",
    "SIMULATION_PARAMETER_LIMIT_EXCEEDED",
    "SIMULATION_PARAMETER_SIZE_LIMIT_EXCEEDED",
    "SIMULATION_STEP_LIMIT_EXCEEDED",
    "STATION_CAPACITY_EXHAUSTED",
    "UNSUPPORTED_SIMULATION_OPTIONS",
    "INVALID_OUTPUT_SELECTION",
    "INVALID_OUTPUT_SAMPLING",
    "UNKNOWN_OUTPUT_VARIABLE",
    "FMU_WORKER_ISOLATION_UNAVAILABLE",
    "FMU_WORKER_START_FAILED",
}


class BaseFmuBackend:
    mode = "unknown"

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

    async def health(self, *, lab_id: Optional[str] = None) -> dict:
        raise NotImplementedError

    async def get_authorized_model_metadata(
        self,
        *,
        claims: dict,
        requested_fmu_filename: Optional[str] = None,
        include_internal_variables: bool = True,
    ) -> ModelMetadata:
        raise NotImplementedError

    async def list_authorized_fmu(self, *, claims: dict) -> dict:
        raise NotImplementedError

    async def get_authorized_parameter_sets(self, *, claims: dict) -> list[dict[str, Any]]:
        return []

    async def get_authorized_experiments(self, *, claims: dict) -> dict[str, Any]:
        self.authorized_access_key(claims)
        return {"resourceSets": [], "truncated": False}

    async def get_authorized_related_resources(self, *, claims: dict) -> dict[str, Any]:
        self.authorized_access_key(claims)
        return {"manifestName": None, "manifestVersion": None, "resources": []}


@dataclass
class LocalFmuMetadataBackend(BaseFmuBackend):
    health_loader: Callable[..., dict]
    model_metadata_loader: Callable[..., ModelMetadata]
    list_loader: Callable[[str], dict]
    related_resources_loader: Optional[Callable[[str], dict[str, Any]]] = None

    mode = "local"

    async def health(self, *, lab_id: Optional[str] = None) -> dict:
        return dict(
            self.health_loader()
            if lab_id is None
            else self.health_loader(lab_id=lab_id)
        )

    async def get_authorized_model_metadata(
        self,
        *,
        claims: dict,
        requested_fmu_filename: Optional[str] = None,
        include_internal_variables: bool = True,
    ) -> ModelMetadata:
        fmu_filename = self.ensure_requested_access_key(claims, requested_fmu_filename)
        return self.model_metadata_loader(
            fmu_filename,
            include_internal_variables=include_internal_variables,
        )

    async def list_authorized_fmu(self, *, claims: dict) -> dict:
        return self.list_loader(self.authorized_access_key(claims))

    async def get_authorized_parameter_sets(self, *, claims: dict) -> list[dict[str, Any]]:
        # Local metadata mode does not execute simulations and has no private
        # Executor endpoint from which to load FMI-LS-REF parameter presets.
        self.authorized_access_key(claims)
        return []

    async def get_authorized_related_resources(self, *, claims: dict) -> dict[str, Any]:
        access_key = self.authorized_access_key(claims)
        if self.related_resources_loader is None:
            return {"manifestName": None, "manifestVersion": None, "resources": []}
        return self.related_resources_loader(access_key)


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
        batch_id: Optional[str] = None,
        parameters: Optional[dict[str, Any]] = None,
        options: Optional[dict[str, Any]] = None,
        input_schedule: Optional[list[dict[str, Any]]] = None,
        scenarios: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        gateway_context = {
            "mode": self.mode,
            "accessKey": access_key,
            "claims": claims,
        }
        authorization_expiry = claims.get("exp")
        if authorization_expiry is not None:
            gateway_context["executionAuthorizationExpiresAt"] = authorization_expiry
        reservation_ends_at = claims.get("reservationEndsAt")
        if reservation_ends_at is not None:
            gateway_context["reservationEndsAt"] = reservation_ends_at
        if lab_id:
            gateway_context["labId"] = lab_id
        if reservation_key:
            gateway_context["reservationKey"] = reservation_key
        payload: dict[str, Any] = {
            "accessKey": access_key,
            "claims": claims,
            "gatewayContext": gateway_context,
            "parameters": parameters or {},
            "options": options or {},
        }
        if sim_id:
            payload["simId"] = sim_id
        if batch_id:
            payload["batchId"] = batch_id
        if scenarios is not None:
            payload["scenarios"] = scenarios
        if input_schedule:
            payload["inputSchedule"] = input_schedule
        if lab_id:
            payload["labId"] = lab_id
        if reservation_key:
            payload["reservationKey"] = reservation_key
        return payload

    @staticmethod
    def _response_error_detail(response: httpx.Response) -> Any:
        # Relay only known short codes and bounded public fields. Never forward
        # paths, URLs, submitted values, or framework diagnostics from Station.
        try:
            payload = response.json()
            detail = payload.get("detail") if isinstance(payload, dict) else None
        except Exception:
            detail = None
        if isinstance(detail, str) and detail in _SAFE_SIMULATION_ERRORS:
            return detail
        if isinstance(detail, dict):
            code = detail.get("code")
            if isinstance(code, str) and code in _SAFE_SIMULATION_ERRORS:
                safe: dict[str, Any] = {"code": code}
                if code == "RESERVATION_DAILY_SCENARIO_LIMIT" and isinstance(detail.get("remaining"), int):
                    safe["remaining"] = max(0, min(10000, detail["remaining"]))
                if code == "BATCH_SIZE_LIMIT_EXCEEDED" and isinstance(detail.get("maximum"), int):
                    safe["maximum"] = max(1, min(20, detail["maximum"]))
                if code == "SIMULATION_NOT_FINISHED" and isinstance(detail.get("status"), str) and detail["status"] in {"queued", "running", "cancelling"}:
                    safe["status"] = detail["status"]
                return safe
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

    async def _request_json(
        self,
        operation: str,
        *,
        access_key: Optional[str] = None,
        public_only: bool = False,
    ) -> dict[str, Any]:
        if not self.base_url:
            raise HTTPException(status_code=503, detail="Station backend is not configured")

        key = ""
        if operation == "health":
            path = "/internal/health"
        elif operation == "capacity":
            path = "/internal/fmu/capacity"
        elif operation in {"describe", "catalog", "parameter-sets", "experiments", "related-resources"}:
            if access_key is None:
                raise HTTPException(status_code=400, detail="Token contains an invalid FMU file key")
            key = str(access_key)
            if not re.fullmatch(
                r"(?:[A-Za-z0-9][A-Za-z0-9._-]{0,127}/)*[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.fmu",
                key,
            ):
                raise HTTPException(status_code=400, detail="Token contains an invalid FMU file key")
            route = {
                "describe": "describe",
                "catalog": "catalog",
                "parameter-sets": "parameter-sets",
                "experiments": "experiments",
                "related-resources": "related-resources",
            }[operation]
            path = f"/internal/fmu/{route}"
        else:
            raise ValueError("Unsupported Station GET operation")

        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.request_timeout) as client:
                request_kwargs: dict[str, Any] = {"headers": self._headers()}
                if operation in {"describe", "catalog", "parameter-sets", "experiments", "related-resources"}:
                    request_kwargs["headers"]["X-FMU-Access-Key"] = key
                if operation == "describe" and public_only:
                    request_kwargs["params"] = {"publicOnly": "true"}
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
        if operation not in {"run", "jobs", "batches"} or not re.fullmatch(
            r"(?:[A-Za-z0-9][A-Za-z0-9._-]{0,127}/)*[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.fmu",
            key,
        ):
            raise HTTPException(status_code=400, detail="Token contains an invalid FMU file key")
        path = {
            "run": "/internal/fmu/simulations/run",
            "jobs": "/internal/fmu/simulations/jobs",
            "batches": "/internal/fmu/simulations/batches",
        }[operation]
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
            input_schedule=request_payload.get("inputSchedule"),
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
            input_schedule=request_payload.get("inputSchedule"),
        )
        return await self._post_json(
            "run",
            access_key=access_key,
            payload=payload,
            authorization=authorization,
        )

    async def submit_authorized_job(
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
        payload = self._json_payload_for_station(
            claims=context["claims"],
            access_key=context["accessKey"],
            lab_id=context["labId"],
            reservation_key=context["reservationKey"],
            sim_id=request_payload.get("simId"),
            parameters=request_payload.get("parameters"),
            options=request_payload.get("options"),
        )
        return await self._post_json(
            "jobs",
            access_key=context["accessKey"],
            payload=payload,
            authorization=authorization,
        )

    async def submit_authorized_batch(
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
        payload = self._json_payload_for_station(
            claims=context["claims"],
            access_key=context["accessKey"],
            lab_id=context["labId"],
            reservation_key=context["reservationKey"],
            batch_id=request_payload.get("batchId"),
            options=request_payload.get("options"),
            scenarios=request_payload.get("scenarios"),
        )
        return await self._post_json(
            "batches",
            access_key=context["accessKey"],
            payload=payload,
            authorization=authorization,
        )

    def _gateway_context_for_scope(
        self,
        *,
        claims: dict,
        requested_lab_id: Optional[str] = None,
        requested_reservation_key: Optional[str] = None,
    ) -> dict[str, Any]:
        context = self.build_authorized_context(
            claims=claims,
            requested_lab_id=requested_lab_id,
            requested_reservation_key=requested_reservation_key,
        )
        return {
            "mode": self.mode,
            "accessKey": context["accessKey"],
            "claims": context["claims"],
            "labId": context["labId"],
            "reservationKey": context["reservationKey"],
        }

    async def _request_scoped_json(
        self,
        operation: str,
        *,
        claims: dict,
        sim_id: Optional[str] = None,
        requested_lab_id: Optional[str] = None,
        requested_reservation_key: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        if not self.base_url:
            raise HTTPException(status_code=503, detail="Station backend is not configured")
        context = self._gateway_context_for_scope(
            claims=claims,
            requested_lab_id=requested_lab_id,
            requested_reservation_key=requested_reservation_key,
        )
        if operation == "history":
            path, method, params = "/internal/fmu/simulations/history", "GET", {"limit": limit, "offset": offset}
        else:
            if not sim_id or not _SIMULATION_ID_RE.fullmatch(sim_id):
                raise HTTPException(status_code=400, detail="INVALID_SIMULATION_ID")
            if operation == "status":
                path, method, params = f"/internal/fmu/simulations/{sim_id}", "GET", None
            elif operation == "result":
                path, method, params = f"/internal/fmu/simulations/{sim_id}/result", "GET", None
            elif operation == "cancel":
                path, method, params = f"/internal/fmu/simulations/{sim_id}/cancel", "POST", None
            else:
                raise ValueError("Unsupported scoped simulation operation")
        encoded_context = base64.urlsafe_b64encode(
            json.dumps(context, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        ).rstrip(b"=").decode("ascii")
        if len(encoded_context) > 12000:
            raise HTTPException(status_code=413, detail="GATEWAY_CONTEXT_TOO_LARGE")
        headers = self._headers()
        headers["X-Gateway-Context"] = encoded_context
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.request_timeout) as client:
                response = await client.request(method, path, headers=headers, params=params)
        except httpx.HTTPError as exc:
            logger.warning("Station backend %s failed: %s", operation, exc)
            raise HTTPException(status_code=503, detail="Station backend unavailable") from exc
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=self._response_error_detail(response))
        try:
            payload = response.json()
        except Exception as exc:
            logger.warning("Station backend returned invalid JSON for %s: %s", operation, exc)
            raise HTTPException(status_code=502, detail="Station backend returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=502, detail="Station backend returned invalid payload")
        return payload

    async def get_authorized_simulation_history(
        self,
        *,
        claims: dict,
        limit: int = 20,
        offset: int = 0,
        requested_lab_id: Optional[str] = None,
        requested_reservation_key: Optional[str] = None,
    ) -> dict[str, Any]:
        return await self._request_scoped_json(
            "history", claims=claims, limit=limit, offset=offset,
            requested_lab_id=requested_lab_id,
            requested_reservation_key=requested_reservation_key,
        )

    async def get_authorized_simulation_status(
        self, *, claims: dict, sim_id: str,
    ) -> dict[str, Any]:
        return await self._request_scoped_json("status", claims=claims, sim_id=sim_id)

    async def get_authorized_simulation_result(
        self, *, claims: dict, sim_id: str,
    ) -> dict[str, Any]:
        return await self._request_scoped_json("result", claims=claims, sim_id=sim_id)

    async def cancel_authorized_simulation(
        self, *, claims: dict, sim_id: str,
    ) -> dict[str, Any]:
        return await self._request_scoped_json("cancel", claims=claims, sim_id=sim_id)

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
        initial = raw.get("initial")
        if isinstance(initial, str) and initial.strip():
            entry["initial"] = initial.strip()[:32]
        nominal = raw.get("nominal")
        if nominal is not None and not isinstance(nominal, bool):
            try:
                normalized_nominal = float(nominal)
            except (TypeError, ValueError, OverflowError):
                normalized_nominal = 0.0
            if math.isfinite(normalized_nominal) and normalized_nominal > 0:
                entry["nominal"] = normalized_nominal
        integer_type = entry["type"] in {
            "Integer", "Enumeration", "Int8", "UInt8", "Int16", "UInt16",
            "Int32", "UInt32", "Int64", "UInt64",
        }
        for bound in ("min", "max"):
            raw_bound = raw.get(bound)
            if raw_bound is None:
                continue
            try:
                value = float(raw_bound)
                if not math.isfinite(value) or (integer_type and not value.is_integer()):
                    continue
                entry[bound] = int(value) if integer_type else value
            except (TypeError, ValueError, OverflowError):
                continue
        description = raw.get("description")
        if isinstance(description, str) and description.strip():
            entry["description"] = description.strip()[:4096]
        display_name = raw.get("displayName")
        if isinstance(display_name, str) and display_name.strip():
            entry["displayName"] = display_name.strip()[:256]
        quantity = raw.get("quantity")
        if isinstance(quantity, str) and quantity.strip():
            entry["quantity"] = quantity.strip()[:256]
        display_unit = raw.get("displayUnit")
        if isinstance(display_unit, str) and display_unit.strip():
            entry["displayUnit"] = display_unit.strip()[:64]
        elif isinstance(display_unit, dict):
            name = display_unit.get("name")
            try:
                factor = float(display_unit.get("factor", 1.0))
                offset = float(display_unit.get("offset", 0.0))
            except (TypeError, ValueError, OverflowError):
                factor = 0.0
                offset = 0.0
            raw_inverse = display_unit.get("inverse", False)
            inverse = raw_inverse is True or str(raw_inverse).strip().lower() in {"true", "1"}
            if (
                isinstance(name, str)
                and name.strip()
                and math.isfinite(factor)
                and factor != 0
                and math.isfinite(offset)
                and (not inverse or offset == 0)
            ):
                normalized_display_unit: dict[str, Any] = {
                    "name": name.strip()[:64],
                    "factor": factor,
                    "offset": offset,
                }
                if inverse:
                    normalized_display_unit["inverse"] = True
                entry["displayUnit"] = normalized_display_unit
        raw_dimensions = raw.get("dimensions")
        if isinstance(raw_dimensions, list) and len(raw_dimensions) <= 64:
            dimensions = []
            for dimension in raw_dimensions:
                if not isinstance(dimension, dict):
                    continue
                normalized_dimension = {}
                for field in ("start", "valueReference"):
                    value = dimension.get(field)
                    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                        normalized_dimension[field] = value
                variable_name = dimension.get("variableName")
                if isinstance(variable_name, str) and variable_name.strip():
                    normalized_dimension["variableName"] = variable_name.strip()[:256]
                if normalized_dimension:
                    dimensions.append(normalized_dimension)
            if dimensions:
                entry["dimensions"] = dimensions
        raw_declared_type = raw.get("declaredType")
        if isinstance(raw_declared_type, dict):
            declared_type = {}
            for field, maximum_length in (
                ("name", 256), ("type", 64), ("description", 4096),
                ("unit", 128), ("quantity", 256), ("displayUnit", 64),
            ):
                value = raw_declared_type.get(field)
                if isinstance(value, str) and value.strip():
                    declared_type[field] = value.strip()[:maximum_length]
            for bound in ("min", "max"):
                value = raw_declared_type.get(bound)
                if value is None or isinstance(value, bool):
                    continue
                try:
                    number = float(value)
                except (TypeError, ValueError, OverflowError):
                    continue
                if math.isfinite(number):
                    declared_type[bound] = int(number) if integer_type and number.is_integer() else number
            raw_items = raw_declared_type.get("items")
            if isinstance(raw_items, list) and len(raw_items) <= 256:
                items = []
                for item in raw_items:
                    if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                        continue
                    raw_value = item.get("value")
                    if raw_value is None or isinstance(raw_value, bool) or not isinstance(raw_value, (str, int, float)):
                        continue
                    try:
                        number = float(raw_value)
                    except (TypeError, ValueError, OverflowError):
                        continue
                    if not math.isfinite(number) or not number.is_integer():
                        continue
                    normalized_item = {"name": item["name"].strip()[:256], "value": int(number)}
                    description = item.get("description")
                    if isinstance(description, str) and description.strip():
                        normalized_item["description"] = description.strip()[:1024]
                    if normalized_item["name"]:
                        items.append(normalized_item)
                if items:
                    declared_type["items"] = items
            if declared_type:
                entry["declaredType"] = declared_type
        enum_items = raw.get("enumItems")
        if entry["type"] == "Enumeration" and isinstance(enum_items, list) and len(enum_items) <= 256:
            normalized_items = []
            for item in enum_items:
                if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                    continue
                raw_value = item.get("value")
                if raw_value is None or isinstance(raw_value, bool) or not isinstance(raw_value, (str, int, float)):
                    continue
                try:
                    numeric_value = float(raw_value)
                except (TypeError, ValueError, OverflowError):
                    continue
                if not math.isfinite(numeric_value) or not numeric_value.is_integer():
                    continue
                value = int(numeric_value)
                normalized_item = {"value": value, "name": item["name"].strip()[:256]}
                item_description = item.get("description")
                if isinstance(item_description, str) and item_description.strip():
                    normalized_item["description"] = item_description.strip()[:1024]
                if normalized_item["name"]:
                    normalized_items.append(normalized_item)
            if normalized_items:
                entry["enumItems"] = normalized_items
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

        def optional_number(name: str) -> Optional[float]:
            value = payload.get(name)
            return float(value) if value is not None else None

        normalized = {
            "modelName": str(payload.get("modelName") or "DecentraLabsProxy"),
            "guid": payload.get("guid"),
            "fmiVersion": str(payload.get("fmiVersion") or "2.0"),
            "simulationKind": str(simulation_kind),
            "simulationType": str(simulation_type),
            "supportsCoSimulation": bool(supports_cs if supports_cs is not None else simulation_kind == "coSimulation"),
            "supportsModelExchange": bool(supports_me if supports_me is not None else simulation_kind == "modelExchange"),
            "defaultStartTime": optional_number("defaultStartTime"),
            "defaultStopTime": optional_number("defaultStopTime"),
            "defaultStepSize": optional_number("defaultStepSize"),
            "modelVariables": [],
        }

        for field, maximum_length in (
            ("description", 4096),
            ("author", 256),
            ("version", 128),
            ("license", 256),
            ("generationTool", 256),
        ):
            value = payload.get(field)
            if isinstance(value, str) and value.strip():
                normalized[field] = value.strip()[:maximum_length]
        default_tolerance = payload.get("defaultTolerance")
        if default_tolerance is not None and not isinstance(default_tolerance, bool):
            try:
                tolerance_value = float(default_tolerance)
            except (TypeError, ValueError, OverflowError):
                tolerance_value = 0.0
            if math.isfinite(tolerance_value) and tolerance_value > 0:
                normalized["defaultTolerance"] = tolerance_value
        raw_capabilities = payload.get("capabilities")
        if isinstance(raw_capabilities, dict):
            capabilities = {}
            for field in (
                "canGetAndSetFMUstate",
                "canSerializeFMUstate",
                "canHandleVariableCommunicationStepSize",
                "providesDirectionalDerivative",
                "providesAdjointDerivatives",
            ):
                value = raw_capabilities.get(field)
                if isinstance(value, bool):
                    capabilities[field] = value
            fixed_step = raw_capabilities.get("fixedInternalStepSize")
            if fixed_step is not None and not isinstance(fixed_step, bool):
                try:
                    fixed_step_value = float(fixed_step)
                except (TypeError, ValueError, OverflowError):
                    fixed_step_value = 0.0
                if math.isfinite(fixed_step_value) and fixed_step_value > 0:
                    capabilities["fixedInternalStepSize"] = fixed_step_value
            if capabilities:
                normalized["capabilities"] = capabilities

        guid = payload.get("guid")
        if guid:
            normalized["guid"] = str(guid)

        for index, variable in enumerate(raw_variables, start=1):
            if not isinstance(variable, dict):
                raise HTTPException(status_code=502, detail="Station backend returned an invalid model variable entry")
            normalized["modelVariables"].append(self._normalize_variable(variable, index))

        fmi_ls_struct = None
        if normalized["fmiVersion"].split(".", 1)[0] == "3":
            fmi_ls_struct = normalize_fmi_ls_struct(
                payload.get("fmiLsStruct"),
                variable_names=[variable["name"] for variable in normalized["modelVariables"]],
            )
        if fmi_ls_struct is not None:
            normalized["fmiLsStruct"] = fmi_ls_struct

        return normalized

    async def health(self, *, lab_id: Optional[str] = None) -> dict:
        checks = {
            "stationConfigured": bool(self.base_url),
            "stationHealth": False,
            "stationAuthentication": False,
        }
        fmu_count = 0
        capacity_payload: dict[str, Any] = {}

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
        else:
            try:
                # /internal/health is deliberately unauthenticated for local
                # supervision.  Capacity is protected and therefore proves
                # that the Gateway token matches the Station token.
                capacity_payload = await self._request_json("capacity")
                checks["stationAuthentication"] = True
            except HTTPException:
                checks["stationAuthentication"] = False

        result = {
            "status": "UP" if all(checks.values()) else "DEGRADED",
            "checks": checks,
            "fmuCount": fmu_count,
            "backendMode": self.mode,
        }
        if isinstance(capacity_payload, dict):
            active = capacity_payload.get("activeExecutions", capacity_payload.get("active"))
            maximum = capacity_payload.get(
                "maxConcurrentExecutions",
                capacity_payload.get("capacity"),
            )
            available = capacity_payload.get(
                "availableCapacity",
                capacity_payload.get("available"),
            )
            if active is not None:
                result["activeExecutions"] = active
            if maximum is not None:
                result["maxConcurrentExecutions"] = maximum
            if available is not None:
                result["availableCapacity"] = available
        return result

    async def get_authorized_model_metadata(
        self,
        *,
        claims: dict,
        requested_fmu_filename: Optional[str] = None,
        include_internal_variables: bool = True,
    ) -> ModelMetadata:
        access_key = self.ensure_requested_access_key(claims, requested_fmu_filename)
        if include_internal_variables:
            payload = await self._request_json("describe", access_key=access_key)
        else:
            payload = await self._request_json("describe", access_key=access_key, public_only=True)
        return self._normalize_model_metadata(payload)

    async def get_authorized_parameter_sets(self, *, claims: dict) -> list[dict[str, Any]]:
        access_key = self.authorized_access_key(claims)
        payload = await self._request_json("parameter-sets", access_key=access_key)
        parameter_presets = payload.get("fmiLsParameterPresets")
        if not isinstance(parameter_presets, list) or len(parameter_presets) > 24:
            raise HTTPException(status_code=502, detail="Station backend returned invalid parameter sets")
        return [preset for preset in parameter_presets if isinstance(preset, dict)]

    async def get_authorized_experiments(self, *, claims: dict) -> dict[str, Any]:
        access_key = self.authorized_access_key(claims)
        payload = await self._request_json("experiments", access_key=access_key)
        resource_sets = payload.get("resourceSets")
        if not isinstance(resource_sets, list) or len(resource_sets) > 8:
            raise HTTPException(status_code=502, detail="Station backend returned invalid FMI-LS-REF experiments")
        return {
            "resourceSets": [resource_set for resource_set in resource_sets if isinstance(resource_set, dict)],
            "truncated": payload.get("truncated") is True,
        }

    async def get_authorized_related_resources(self, *, claims: dict) -> dict[str, Any]:
        access_key = self.authorized_access_key(claims)
        payload = await self._request_json("related-resources", access_key=access_key)
        resources = payload.get("resources")
        if not isinstance(resources, list) or len(resources) > 128:
            raise HTTPException(status_code=502, detail="Station backend returned invalid FMI-LS-REF resources")

        normalized = []
        for resource in resources:
            if not isinstance(resource, dict):
                continue
            source = resource.get("source")
            if not isinstance(source, str) or not source.strip() or len(source) > 2048:
                continue
            labels = resource.get("labels")
            normalized_labels = []
            if isinstance(labels, list):
                for label in labels[:32]:
                    if not isinstance(label, dict):
                        continue
                    name = label.get("name")
                    if not isinstance(name, str) or not name.strip():
                        continue
                    description = label.get("description")
                    normalized_labels.append({
                        "name": name.strip()[:256],
                        "description": description.strip()[:1024] if isinstance(description, str) else "",
                    })
            normalized.append({
                "id": str(resource.get("id") or "")[:64],
                "role": str(resource.get("role") or "")[:128],
                "type": str(resource.get("type") or "")[:256],
                "source": source.strip(),
                "description": str(resource.get("description") or "")[:2048],
                "labels": normalized_labels,
                "availableInFmu": resource.get("availableInFmu") is True,
            })

        manifest_name = payload.get("manifestName")
        manifest_version = payload.get("manifestVersion")
        return {
            "manifestName": manifest_name if isinstance(manifest_name, str) else None,
            "manifestVersion": manifest_version[:64] if isinstance(manifest_version, str) else None,
            "resources": normalized,
        }

    async def list_authorized_fmu(self, *, claims: dict) -> dict:
        access_key = self.authorized_access_key(claims)
        try:
            payload = await self._request_json("catalog", access_key=access_key)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            metadata = await self.get_authorized_model_metadata(
                claims=claims,
                requested_fmu_filename=access_key,
                include_internal_variables=False,
            )
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
