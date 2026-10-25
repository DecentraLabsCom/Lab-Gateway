"""Resolve and compile FMI access policies stored in associated AAS resources."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Mapping

import httpx

from simulation_access_policy import build_effective_policy, compile_part4_access_rules


_ACCESS_CONTROL_SEMANTIC_ID = "urn:decentralabs:aas:SimulationAccessControl:1"
_MAX_LINK_BYTES = 65_536
_MAX_SUBMODELS = 128
_CACHE_TTL_SECONDS = 5.0
_MAX_CACHE_ENTRIES = 512


class AasAccessPolicyResolver:
    """Load the per-lab AAS policy with a short bounded cache.

    Link files and AAS URLs are administrative Gateway configuration. A linked
    AAS that cannot be read fails closed; an accessible AAS with no access
    control profile uses the FMI-derived default policy.
    """

    def __init__(
        self,
        *,
        get_basyx_url: Callable[[], str],
        get_request_headers: Callable[[], Mapping[str, str]],
        get_link_path: Callable[[str], Path],
        client_factory: Callable[..., Any] = httpx.AsyncClient,
        cache_ttl_seconds: float = _CACHE_TTL_SECONDS,
        max_cache_entries: int = _MAX_CACHE_ENTRIES,
    ):
        self.get_basyx_url = get_basyx_url
        self.get_request_headers = get_request_headers
        self.get_link_path = get_link_path
        self.client_factory = client_factory
        self.cache_ttl_seconds = max(0.0, min(float(cache_ttl_seconds), 60.0))
        self.max_cache_entries = max(1, min(int(max_cache_entries), _MAX_CACHE_ENTRIES))
        self._cache: OrderedDict[str, tuple[float, dict[str, Any] | None]] = OrderedDict()

    @staticmethod
    def _claim_text(claims: Mapping[str, Any], name: str) -> str:
        value = claims.get(name)
        return str(value).strip() if value is not None else ""

    def _read_link(self, claims: Mapping[str, Any]) -> dict[str, Any] | None:
        access_key = self._claim_text(claims, "accessKey")
        lab_id = self._claim_text(claims, "labId")
        for key in dict.fromkeys(value for value in (access_key, lab_id) if value):
            try:
                path = self.get_link_path(key)
            except Exception as exc:
                # FMU access keys commonly contain a relative path and cannot
                # be used as a one-segment link filename. A lab ID is also
                # carried in the reservation claims, so use that safe index
                # before treating the link as unavailable.
                if key != lab_id and lab_id:
                    continue
                raise RuntimeError("AAS link record is unavailable") from exc
            if not path.is_file():
                continue
            try:
                raw = path.read_bytes()
                if len(raw) > _MAX_LINK_BYTES:
                    raise ValueError("AAS link record exceeds its size limit")
                link = json.loads(raw.decode("utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
                raise RuntimeError("AAS link record is unavailable") from exc
            if not isinstance(link, dict):
                raise RuntimeError("AAS link record is invalid")
            target_id = link.get("aasId")
            linked_lab = str(link.get("labId") or "").strip()
            if not isinstance(target_id, str) or not target_id.strip() or len(target_id) > 2048:
                raise RuntimeError("AAS link record is invalid")
            if linked_lab and linked_lab != lab_id:
                raise RuntimeError("AAS link does not match the authorized laboratory")
            raw_submodel_ids = link.get("submodelIds", [])
            if not isinstance(raw_submodel_ids, list) or len(raw_submodel_ids) > _MAX_SUBMODELS:
                raise RuntimeError("AAS link submodel list is invalid")
            if any(
                not isinstance(value, str) or not value.strip() or len(value) > 2048
                for value in raw_submodel_ids
            ):
                raise RuntimeError("AAS link submodel list is invalid")
            submodel_ids = [value.strip() for value in raw_submodel_ids]
            raw_access_control_submodel_id = link.get("accessControlSubmodelId")
            if raw_access_control_submodel_id is not None and (
                not isinstance(raw_access_control_submodel_id, str)
                or not raw_access_control_submodel_id.strip()
                or len(raw_access_control_submodel_id) > 2048
            ):
                raise RuntimeError("AAS link access-control submodel is invalid")
            return {
                "aasId": target_id.strip(),
                "submodelIds": list(dict.fromkeys(submodel_ids)),
                "accessControlSubmodelId": (
                    raw_access_control_submodel_id.strip()
                    if isinstance(raw_access_control_submodel_id, str)
                    else None
                ),
            }
        return None

    @staticmethod
    def _encode_id(value: str) -> str:
        return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")

    @staticmethod
    def _submodel_ids(shell: Mapping[str, Any]) -> list[str]:
        raw_refs = shell.get("submodels", shell.get("submodelIds", []))
        if not isinstance(raw_refs, list) or len(raw_refs) > _MAX_SUBMODELS:
            raise RuntimeError("AAS shell has an invalid submodel list")
        result = []
        for reference in raw_refs:
            if isinstance(reference, str):
                values = [reference]
            elif isinstance(reference, Mapping):
                keys = reference.get("keys", [])
                values = [
                    key.get("value")
                    for key in keys
                    if isinstance(key, Mapping) and key.get("type") in {"Submodel", "GlobalReference"}
                ] if isinstance(keys, list) else []
                if isinstance(reference.get("id"), str):
                    values.append(reference["id"])
            else:
                values = []
            for value in values:
                if not isinstance(value, str) or not value.strip() or len(value) > 2048:
                    continue
                if value.strip() not in result:
                    result.append(value.strip())
        return result

    @staticmethod
    def _is_access_control_submodel(
        payload: Mapping[str, Any],
        explicit_submodel_id: str | None = None,
    ) -> bool:
        if explicit_submodel_id and payload.get("id") == explicit_submodel_id:
            return True
        semantic = payload.get("semanticId")
        if isinstance(semantic, Mapping):
            keys = semantic.get("keys", [])
            if isinstance(keys, list) and any(
                isinstance(key, Mapping) and key.get("value") == _ACCESS_CONTROL_SEMANTIC_ID
                for key in keys
            ):
                return True
        if payload.get("idShort") == "SimulationAccessControl":
            return True
        elements = payload.get("submodelElements")
        return isinstance(elements, list) and any(
            isinstance(element, Mapping) and AasAccessPolicyResolver._is_json_access_rules_blob(element)
            for element in elements
        )

    @staticmethod
    def _is_json_access_rules_blob(blob: Mapping[str, Any]) -> bool:
        if blob.get("modelType") != "Blob" or str(blob.get("contentType") or "").lower() != "application/json":
            return False
        raw_value = blob.get("value")
        if not isinstance(raw_value, str) or len(raw_value) > 2 * 1_048_576:
            return False
        try:
            raw_rules = base64.b64decode(raw_value, validate=True)
            if len(raw_rules) > 1_048_576:
                return False
            document = json.loads(raw_rules.decode("utf-8"))
        except (ValueError, UnicodeError, json.JSONDecodeError):
            return False
        return isinstance(document, Mapping) and set(document) == {"AllAccessPermissionRules"}

    @classmethod
    def _find_access_blob(
        cls,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        elements = payload.get("submodelElements")
        if not isinstance(elements, list) or len(elements) > 128:
            raise RuntimeError("AAS access control submodel is invalid")
        blobs = [
            element for element in elements
            if isinstance(element, Mapping)
            and (
                element.get("idShort") == "AllAccessPermissionRules"
                or cls._is_json_access_rules_blob(element)
            )
        ]
        if len(blobs) != 1:
            raise RuntimeError("AAS access control submodel must contain one rules Blob")
        blob = blobs[0]
        if blob.get("modelType") != "Blob" or str(blob.get("contentType") or "").lower() != "application/json":
            raise RuntimeError("AAS access rules must be an application/json Blob")
        return blob

    @staticmethod
    def _property(payload: Mapping[str, Any], id_short: str) -> str | None:
        matches = [
            element for element in payload.get("submodelElements", [])
            if isinstance(element, Mapping) and element.get("idShort") == id_short
        ]
        if not matches:
            return None
        if len(matches) != 1 or matches[0].get("modelType") != "Property":
            raise RuntimeError("AAS access control digest property is invalid")
        value = matches[0].get("value")
        return value if isinstance(value, str) else None

    async def _load_access_submodel(
        self,
        *,
        basyx_url: str,
        target_aas_id: str,
        hinted_submodel_ids: list[str],
        access_control_submodel_id: str | None,
        lab_id: str,
    ) -> dict[str, Any] | None:
        try:
            headers = dict(self.get_request_headers())
            async with self.client_factory(
                base_url=basyx_url,
                headers=headers,
                timeout=8.0,
            ) as client:
                shell_response = await client.get(f"/shells/{self._encode_id(target_aas_id)}")
                if shell_response.status_code == 404:
                    raise FileNotFoundError("AAS shell does not exist")
                if shell_response.status_code != 200:
                    raise RuntimeError("AAS shell cannot be read")
                shell = shell_response.json()
                if not isinstance(shell, Mapping) or shell.get("id") != target_aas_id:
                    raise RuntimeError("AAS shell response is invalid")
                referenced_ids = self._submodel_ids(shell)
                policy_submodel_id = f"urn:decentralabs:lab:{lab_id}:sm:simulationAccessControl"
                if access_control_submodel_id and access_control_submodel_id not in referenced_ids:
                    raise RuntimeError("AAS link access-control submodel is outside the linked shell")
                if any(value not in referenced_ids and value != policy_submodel_id for value in hinted_submodel_ids):
                    raise RuntimeError("AAS link references a submodel outside its shell")
                candidate_ids = (
                    [access_control_submodel_id]
                    if access_control_submodel_id
                    else list(dict.fromkeys([*hinted_submodel_ids, *referenced_ids]))
                )
                policy_submodels = []
                for submodel_id in candidate_ids:
                    response = await client.get(f"/submodels/{self._encode_id(submodel_id)}")
                    if response.status_code == 404:
                        continue
                    if response.status_code != 200:
                        raise RuntimeError("AAS submodel cannot be read")
                    payload = response.json()
                    if not isinstance(payload, Mapping):
                        raise RuntimeError("AAS submodel response is invalid")
                    if payload.get("id") != submodel_id:
                        raise RuntimeError("AAS submodel ID does not match its reference")
                    if self._is_access_control_submodel(payload, access_control_submodel_id):
                        policy_submodels.append(payload)
                if len(policy_submodels) > 1:
                    raise RuntimeError("AAS shell has ambiguous access control submodels")
                if not policy_submodels:
                    if access_control_submodel_id:
                        raise RuntimeError("Configured AAS access policy submodel does not exist")
                    return None

                submodel = policy_submodels[0]
                blob = self._find_access_blob(submodel)
                if blob is None:
                    raise RuntimeError("AAS access control submodel has no rules Blob")
                raw_value = blob.get("value")
                if not isinstance(raw_value, str) or len(raw_value) > 2 * 1_048_576:
                    raise RuntimeError("AAS access rules Blob exceeds its size limit")
                try:
                    raw_rules = base64.b64decode(raw_value, validate=True)
                    if len(raw_rules) > 1_048_576:
                        raise ValueError("Blob too large")
                    document = json.loads(raw_rules.decode("utf-8"))
                except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
                    raise RuntimeError("AAS access rules Blob is invalid") from exc
                interface_digest = self._property(submodel, "InterfaceDigest")
                generated_digest = self._property(submodel, "GeneratedPolicyDigest")
                actual_blob_digest = hashlib.sha256(raw_rules).hexdigest()
                source = "aas-generated" if generated_digest and generated_digest == actual_blob_digest else "aas-provider"
                return {
                    "document": document,
                    "interfaceDigest": interface_digest,
                    "source": source,
                    "submodelId": str(submodel.get("id") or ""),
                    "referencedSubmodelIds": referenced_ids,
                }
        except FileNotFoundError:
            raise
        except (httpx.RequestError, ValueError, RuntimeError) as exc:
            raise RuntimeError("AAS access policy is unavailable") from exc

    def _cache_get(self, key: str) -> tuple[bool, dict[str, Any] | None]:
        entry = self._cache.get(key)
        if entry is None:
            return False, None
        expires_at, value = entry
        if expires_at <= time.monotonic():
            self._cache.pop(key, None)
            return False, None
        self._cache.move_to_end(key)
        return True, value

    def _cache_set(self, key: str, value: dict[str, Any] | None) -> None:
        if self.cache_ttl_seconds <= 0:
            return
        self._cache[key] = (time.monotonic() + self.cache_ttl_seconds, value)
        self._cache.move_to_end(key)
        while len(self._cache) > self.max_cache_entries:
            self._cache.popitem(last=False)

    def invalidate(self, lab_id: str | None = None) -> None:
        if lab_id is None:
            self._cache.clear()
            return
        prefix = f"{lab_id}:"
        for key in list(self._cache):
            if key.startswith(prefix):
                self._cache.pop(key, None)

    async def resolve(self, claims: Mapping[str, Any], metadata: Mapping[str, Any]) -> dict[str, Any]:
        fallback = build_effective_policy(metadata)
        lab_id = self._claim_text(claims, "labId")
        access_key = self._claim_text(claims, "accessKey")
        if not lab_id or not access_key:
            raise RuntimeError("authorized FMU claims are incomplete")
        link = self._read_link(claims)
        target_id = link["aasId"] if link else f"urn:decentralabs:lab:{lab_id}"
        basyx_url = str(self.get_basyx_url() or "").rstrip("/")
        if not basyx_url:
            if link:
                raise RuntimeError("linked AAS access policy is unavailable")
            return fallback

        cache_key = f"{lab_id}:{target_id}"
        cached, policy_data = self._cache_get(cache_key)
        if not cached:
            hinted_submodel_ids: list[str] = []
            access_control_submodel_id: str | None = None
            if link is not None:
                hinted_submodel_ids = link["submodelIds"]
                access_control_submodel_id = link["accessControlSubmodelId"]
            try:
                policy_data = await self._load_access_submodel(
                    basyx_url=basyx_url,
                    target_aas_id=target_id,
                    hinted_submodel_ids=hinted_submodel_ids,
                    access_control_submodel_id=access_control_submodel_id,
                    lab_id=lab_id,
                )
            except FileNotFoundError as exc:
                if link:
                    raise RuntimeError("linked AAS access policy is unavailable") from exc
                return fallback
            self._cache_set(cache_key, policy_data)
        if policy_data is None:
            return fallback
        try:
            return compile_part4_access_rules(
                policy_data["document"],
                metadata,
                None,
                declared_interface_digest=policy_data["interfaceDigest"],
                claims=claims,
                source=policy_data["source"],
                allowed_submodel_ids=set(policy_data["referencedSubmodelIds"]),
            )
        except ValueError as exc:
            if "stale" in str(exc).lower():
                raise RuntimeError("AAS FMI access policy is stale") from exc
            raise RuntimeError("AAS FMI access policy is invalid") from exc
        except (KeyError, TypeError) as exc:
            raise RuntimeError("AAS FMI access policy is invalid") from exc

    async def inspect(self, claims: Mapping[str, Any], metadata: Mapping[str, Any]) -> dict[str, Any]:
        """Return an admin-safe policy status summary without exposing the rules."""
        lab_id = self._claim_text(claims, "labId")
        try:
            link = self._read_link(claims)
        except RuntimeError:
            return {
                "state": "invalid",
                "policySource": "unavailable",
                "message": "The saved AAS link is invalid. Review and save the link again before relying on its access rules.",
                "aasLinked": True,
                "regenerationAvailable": False,
                "readableVariableCount": 0,
                "writableVariableCount": 0,
            }
        canonical_shell_id = f"urn:decentralabs:lab:{lab_id}" if lab_id else ""
        managed = not link or link["aasId"] == canonical_shell_id
        try:
            policy = await self.resolve(claims, metadata)
        except RuntimeError as exc:
            message = str(exc).lower()
            state = "stale" if "stale" in message else "invalid" if "invalid" in message else "unavailable"
            user_message = {
                "stale": "The saved AAS access rules do not match the current FMU interface. Update the AAS rules or regenerate defaults.",
                "invalid": "The AAS access rules are invalid or refer to variables that do not match this FMU. Review the linked policy.",
                "unavailable": "The linked AAS or its access rules could not be read. Check the AAS endpoint, credentials and policy submodel reference.",
            }[state]
            return {
                "state": state,
                "policySource": "unavailable",
                "message": user_message,
                "aasLinked": bool(link),
                "regenerationAvailable": managed and state in {"stale", "invalid"},
                "readableVariableCount": 0,
                "writableVariableCount": 0,
            }

        permissions = policy.get("variables", {})
        readable_count = sum(
            1 for permission in permissions.values()
            if isinstance(permission, Mapping) and permission.get("read") is True
        ) if isinstance(permissions, Mapping) else 0
        writable_count = sum(
            1 for permission in permissions.values()
            if isinstance(permission, Mapping) and bool(permission.get("writeAt"))
        ) if isinstance(permissions, Mapping) else 0
        source = str(policy.get("policySource") or "fmi-default")
        state = {
            "aas-generated": "generated",
            "aas-provider": "customized",
            "fmi-default": "fmi-default",
        }.get(source, "unavailable")
        user_message = {
            "generated": "Gateway-generated AAS access rules are active.",
            "customized": "Provider-defined AAS access rules are active.",
            "fmi-default": (
                "The linked AAS has no compatible variable access policy; FMI-derived defaults are active."
                if link else "No AAS access policy is linked; FMI-derived defaults are active."
            ),
            "unavailable": "The effective AAS access policy is unavailable.",
        }[state]
        return {
            "state": state,
            "policySource": source,
            "message": user_message,
            "aasLinked": bool(link),
            "regenerationAvailable": managed and state in {"generated", "customized", "fmi-default"},
            "readableVariableCount": readable_count,
            "writableVariableCount": writable_count,
        }


__all__ = ["AasAccessPolicyResolver"]
