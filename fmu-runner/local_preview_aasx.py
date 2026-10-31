"""Create and link one ephemeral AASX package for each local FMU preview."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4


_LAB_ID_RE = re.compile(r"local_demo_[a-f0-9]{24}")
_SHELL_ID_PREFIX = "urn:decentralabs:lab:"
_SUBMODEL_ID_FIELDS = (
    "submodelId",
    "technicalDataSubmodelId",
    "executionSubmodelId",
    "interfacesSubmodelId",
    "contactSubmodelId",
    "handoverSubmodelId",
    "fmiLsRelatedResourcesSubmodelId",
    "accessControlSubmodelId",
)


class LocalPreviewAasxRegistry:
    """Provision a generated FMI AASX, import it, and link it to preview claims.

    The first sync gives BaSyx a complete generated shell. The subsequent
    serialization and AASX sync exercise the same package import path used by
    Lab Manager. The resulting link is scoped to the stable synthetic preview
    lab ID, never to an operational FMU access key.
    """

    def __init__(
        self,
        *,
        get_model_metadata: Callable[..., Any],
        sync_fmu_to_basyx: Callable[..., Any],
        serialize_aasx_resources: Callable[..., Any],
        record_aasx: Callable[..., Any],
        get_aasx_package: Callable[[str], Any],
        get_link_path: Callable[[str], Path],
        build_aas_shell: Callable[..., dict],
        get_effective_policy: Callable[[dict], Any],
        invalidate_access_policy: Callable[..., Any],
        get_digital_twin_assets: Callable[[str, str], Any] | None = None,
        get_fmi_ls_related_resources: Callable[[str], Any] | None = None,
    ):
        self.get_model_metadata = get_model_metadata
        self.sync_fmu_to_basyx = sync_fmu_to_basyx
        self.serialize_aasx_resources = serialize_aasx_resources
        self.record_aasx = record_aasx
        self.get_aasx_package = get_aasx_package
        self.get_link_path = get_link_path
        self.build_aas_shell = build_aas_shell
        self.get_effective_policy = get_effective_policy
        self.invalidate_access_policy = invalidate_access_policy
        self.get_digital_twin_assets = get_digital_twin_assets
        self.get_fmi_ls_related_resources = get_fmi_ls_related_resources
        self._locks: dict[str, asyncio.Lock] = {}
        self._cache: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _validate_claims(claims: dict) -> tuple[str, str]:
        if not isinstance(claims, dict) or claims.get("sub") != "local-preview":
            raise RuntimeError("Local AASX provisioning requires preview claims")
        lab_id = str(claims.get("labId") or "")
        access_key = str(claims.get("accessKey") or "")
        if _LAB_ID_RE.fullmatch(lab_id) is None or not access_key:
            raise RuntimeError("Local FMU preview claims are invalid")
        expected = f"local_demo_{hashlib.sha256(access_key.encode()).hexdigest()[:24]}"
        if lab_id != expected:
            raise RuntimeError("Local AASX lab identity does not match its FMU")
        return lab_id, access_key

    @staticmethod
    def _submodel_ids(shell: dict) -> list[str]:
        result: list[str] = []
        for reference in shell.get("submodels", []):
            if not isinstance(reference, dict):
                continue
            for key in reference.get("keys", []):
                value = key.get("value") if isinstance(key, dict) else None
                if isinstance(value, str) and value.strip() and value not in result:
                    result.append(value)
        return result

    @staticmethod
    def _require_sync(result: Any, operation: str) -> dict:
        if not isinstance(result, dict) or result.get("error") or result.get("disabled"):
            reason = str(result.get("error") or "unavailable") if isinstance(result, dict) else "unavailable"
            raise RuntimeError(f"Local AASX {operation} failed: {reason[:240]}")
        return result

    async def ensure(self, claims: dict) -> dict:
        lab_id, access_key = self._validate_claims(claims)
        lock = self._locks.setdefault(lab_id, asyncio.Lock())
        async with lock:
            cached = self._cache.get(lab_id)
            if cached is not None:
                return dict(cached)

            raw_assets = self.get_digital_twin_assets(lab_id, access_key) if self.get_digital_twin_assets else []
            if raw_assets is None:
                raw_assets = []
            if not isinstance(raw_assets, list) or len(raw_assets) > 2:
                raise RuntimeError("Local digital twin asset references are invalid")
            assets: list[dict[str, str]] = []
            for raw_asset in raw_assets:
                if not isinstance(raw_asset, dict):
                    raise RuntimeError("Local digital twin asset reference is invalid")
                asset_path = str(raw_asset.get("path") or "").strip()
                content_type = str(raw_asset.get("contentType") or "").strip().lower()
                valid_app = (
                    content_type == "text/html"
                    and re.fullmatch(
                        rf"/digital-twin-apps/{re.escape(lab_id)}/[a-f0-9]{{64}}/index\.html",
                        asset_path,
                    ) is not None
                )
                valid_scene = (
                    content_type == "model/gltf-binary"
                    and re.fullmatch(
                        rf"/digital-twin-scenes/{re.escape(lab_id)}/[a-f0-9]{{64}}\.glb",
                        asset_path,
                    ) is not None
                )
                if not (valid_app or valid_scene) or any(asset["path"] == asset_path for asset in assets):
                    raise RuntimeError("Local digital twin asset reference is invalid")
                assets.append({"path": asset_path, "contentType": content_type})
            asset_urls = [asset["path"] for asset in assets]

            link_path = self.get_link_path(lab_id)
            if link_path.exists():
                if self.get_aasx_package(lab_id) is None:
                    raise RuntimeError("Local AASX link has no package record")
                try:
                    existing_link = json.loads(link_path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                    raise RuntimeError("Local AASX link is unavailable") from exc
                stored_asset_urls = (
                    existing_link.get("digitalTwinAssetUrls")
                    if isinstance(existing_link, dict)
                    else None
                )
                if not isinstance(stored_asset_urls, list):
                    legacy_asset_url = (
                        str(existing_link.get("digitalTwinAssetUrl") or "").strip()
                        if isinstance(existing_link, dict)
                        else ""
                    )
                    stored_asset_urls = [legacy_asset_url] if legacy_asset_url else []
                if isinstance(existing_link, dict) and stored_asset_urls == asset_urls:
                    policy = await self.get_effective_policy(claims)
                    if not isinstance(policy, dict) or not str(policy.get("policySource") or "").startswith("aas-"):
                        raise RuntimeError("Linked local AASX policy is unavailable")
                    self._cache[lab_id] = dict(policy)
                    return dict(policy)

            metadata = await self.get_model_metadata(access_key)
            if not isinstance(metadata, dict) or not isinstance(metadata.get("modelVariables"), list):
                raise RuntimeError("Local FMU metadata is unavailable")
            fmi_ls_resources = None
            if self.get_fmi_ls_related_resources is not None:
                fmi_ls_resources = await self.get_fmi_ls_related_resources(access_key)

            extra_info: dict[str, Any] = {"description": "Local-only digital twin access-policy validation."}
            if assets:
                extra_info["digitalTwinAssets"] = [
                    {"url": asset["path"], "contentType": asset["contentType"]}
                    for asset in assets
                ]

            generated = self._require_sync(await self.sync_fmu_to_basyx(
                lab_id=lab_id,
                access_key=access_key,
                metadata=metadata,
                extra_info=extra_info,
                fmi_ls_resources=fmi_ls_resources,
            ), "metadata sync")
            shell_id = generated.get("aasId")
            if not isinstance(shell_id, str) or shell_id != f"{_SHELL_ID_PREFIX}{lab_id}":
                raise RuntimeError("Local AAS shell identity is invalid")
            shell = self.build_aas_shell(
                lab_id,
                access_key,
                metadata,
                extra_info=extra_info,
                fmi_ls_resources=fmi_ls_resources,
            )
            submodel_ids = self._submodel_ids(shell)
            if not submodel_ids or not generated.get("accessControlSubmodelId"):
                raise RuntimeError("Generated AAS shell has no FMI access-control submodel")

            serialization = await self.serialize_aasx_resources(
                shell_ids=[shell_id],
                submodel_ids=submodel_ids,
            )
            if (
                not isinstance(serialization, dict)
                or serialization.get("error")
                or not isinstance(serialization.get("content"), (bytes, bytearray))
                or not serialization["content"]
            ):
                raise RuntimeError("Local AASX package could not be serialized")
            package = bytes(serialization["content"])

            imported = self._require_sync(await self.sync_fmu_to_basyx(
                lab_id=lab_id,
                access_key=access_key,
                metadata=metadata,
                aasx_bytes=package,
                fmi_ls_resources=fmi_ls_resources,
                required_aas_id=shell_id,
            ), "package import")
            if imported.get("accessPolicyPreserved") is not True:
                raise RuntimeError("Imported local AASX access policy was not preserved")

            self.record_aasx(
                lab_id=lab_id,
                filename=f"{lab_id}.aasx",
                content=package,
                sync_result=imported,
            )
            resolved_submodel_ids = imported.get("uploadedSubmodelIds")
            if not isinstance(resolved_submodel_ids, list):
                resolved_submodel_ids = submodel_ids
            link = {
                "aasId": shell_id,
                "labId": lab_id,
                "submodelIds": resolved_submodel_ids,
                "accessControlSubmodelId": imported.get("accessControlSubmodelId"),
                "digitalTwinAssetUrls": asset_urls,
            }
            link_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = link_path.with_name(f".{link_path.name}.{uuid4().hex}.tmp")
            try:
                temporary_path.write_text(json.dumps(link, indent=2), encoding="utf-8")
                os.replace(temporary_path, link_path)
            finally:
                temporary_path.unlink(missing_ok=True)

            self.invalidate_access_policy(lab_id)
            policy = await self.get_effective_policy(claims)
            if not isinstance(policy, dict) or not str(policy.get("policySource") or "").startswith("aas-"):
                raise RuntimeError("Imported local AASX policy could not be resolved")
            self._cache[lab_id] = dict(policy)
            return dict(policy)


__all__ = ["LocalPreviewAasxRegistry"]
