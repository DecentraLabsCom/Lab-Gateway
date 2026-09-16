"""Resolve provider-laboratory AAS associations from current Gateway state.

The BaSyx repository is the source of truth for generated and imported AAS
resources.  The local catalog contributes only the provenance metadata of an
imported AASX package, while link files contribute external-link metadata.
"""

import json
import re
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional


_LAB_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_AAS_ID_PREFIX = "urn:decentralabs:lab:"


def _unique_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip()
    ))


def _safe_lab_id(value: Any) -> Optional[str]:
    lab_id = str(value or "").strip()
    return lab_id if _LAB_ID_RE.fullmatch(lab_id) else None


def _association_source(value: Any, default: str = "imported") -> str:
    source = str(value or default).strip().lower()
    return source if source in {"generated", "imported", "linked"} else default


class AasAssociationService:
    """Combine imported metadata, AAS links and live BaSyx shells."""

    def __init__(
        self,
        *,
        package_catalog: Any,
        link_data_path: Path,
        discover_basyx_shells: Callable[[], Awaitable[dict[str, Any]]],
        delete_resources: Callable[..., Awaitable[dict[str, Any]]],
    ):
        self.package_catalog = package_catalog
        self.link_data_path = Path(link_data_path)
        self.discover_basyx_shells = discover_basyx_shells
        self.delete_resources = delete_resources

    def _imported_associations(self) -> dict[str, dict[str, Any]]:
        associations: dict[str, dict[str, Any]] = {}
        for package in self.package_catalog.list_packages():
            lab_id = _safe_lab_id(package.get("labId"))
            if not lab_id:
                continue
            association = dict(package)
            association.update({
                "labId": lab_id,
                "source": "imported",
                "associationType": "imported",
                "shellIds": _unique_strings(package.get("shellIds")),
                "submodelIds": _unique_strings(package.get("submodelIds")),
                "canDownload": True,
                "canDelete": True,
            })
            associations[lab_id] = association
        return associations

    def _read_link_file(self, path: Path) -> Optional[dict[str, Any]]:
        try:
            link = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            return None
        if not isinstance(link, dict):
            return None
        lab_id = _safe_lab_id(link.get("labId"))
        aas_id = link.get("aasId")
        if not lab_id or not isinstance(aas_id, str) or not aas_id.strip():
            return None
        target_aas_id = aas_id.strip()[:2048]
        return {
            "labId": lab_id,
            "source": "linked",
            "associationType": "linked",
            "targetAasId": target_aas_id,
            "shellIds": [target_aas_id],
            "submodelIds": _unique_strings(link.get("submodelIds")),
            "storage": "external",
            "archiveStored": False,
            "canDownload": True,
            "canDelete": True,
        }

    def _linked_associations(self) -> dict[str, dict[str, Any]]:
        if not self.link_data_path.is_dir():
            return {}
        candidates: dict[str, list[tuple[bool, dict[str, Any]]]] = {}
        for path in sorted(self.link_data_path.glob("*.aas-link.json")):
            association = self._read_link_file(path)
            if association is None:
                continue
            lab_id = association["labId"]
            candidates.setdefault(lab_id, []).append((path.name == f"{lab_id}.aas-link.json", association))

        result: dict[str, dict[str, Any]] = {}
        for lab_id, values in candidates.items():
            # Prefer the labId-indexed record over an access-key mirror when
            # both exist for the same link.
            values.sort(key=lambda value: value[0], reverse=True)
            result[lab_id] = values[0][1]
        return result

    @staticmethod
    def _generated_associations(shells: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(shells, list):
            return {}
        result: dict[str, dict[str, Any]] = {}
        for shell in shells:
            if not isinstance(shell, dict):
                continue
            shell_id = shell.get("id")
            if not isinstance(shell_id, str) or not shell_id.startswith(_AAS_ID_PREFIX):
                continue
            lab_id = _safe_lab_id(shell_id[len(_AAS_ID_PREFIX):])
            if not lab_id:
                continue
            submodel_ids = _unique_strings(shell.get("submodelIds"))
            result[lab_id] = {
                "labId": lab_id,
                "source": "generated",
                "associationType": "generated",
                "storage": "basyx",
                "archiveStored": False,
                "shellIds": [shell_id],
                "submodelIds": submodel_ids,
                "canDownload": True,
                "canDelete": True,
            }
        return result

    async def list_associations(self) -> dict[str, Any]:
        imported = self._imported_associations()
        linked = self._linked_associations()
        associations = dict(imported)

        discovery = await self.discover_basyx_shells()
        if not isinstance(discovery, dict):
            discovery = {"error": "BaSyx shell discovery failed"}
        warning = str(discovery.get("error") or "").strip()
        if not warning:
            generated = self._generated_associations(discovery.get("shells"))
            for lab_id, association in generated.items():
                associations.setdefault(lab_id, association)

        # A link is the effective association even if a generated shell for
        # the same lab remains in BaSyx underneath it. Removing the link must
        # reveal that generated shell again, not delete it.
        associations.update(linked)
        response: dict[str, Any] = {
            "associations": sorted(
                associations.values(),
                key=lambda association: str(association.get("labId", "")),
            ),
            "basyxAvailable": not bool(discovery.get("disabled")) and not bool(warning),
        }
        if warning:
            response["warning"] = warning
        return response

    async def get_association(self, lab_id: str) -> Optional[dict[str, Any]]:
        safe_lab_id = _safe_lab_id(lab_id)
        if not safe_lab_id:
            return None
        result = await self.list_associations()
        return next(
            (
                association
                for association in result["associations"]
                if association.get("labId") == safe_lab_id
            ),
            None,
        )

    def _remove_link_files(self, lab_id: str) -> bool:
        removed = False
        if not self.link_data_path.is_dir():
            return False
        for path in self.link_data_path.glob("*.aas-link.json"):
            link = self._read_link_file(path)
            if link and link.get("labId") == lab_id:
                path.unlink(missing_ok=True)
                removed = True
        return removed

    async def delete_association(self, lab_id: str) -> Optional[dict[str, Any]]:
        association = await self.get_association(lab_id)
        if association is None:
            # A link can still be removed while BaSyx discovery is unavailable.
            safe_lab_id = _safe_lab_id(lab_id)
            if safe_lab_id and self._remove_link_files(safe_lab_id):
                return {
                    "deleted": True,
                    "unlinked": True,
                    "labId": safe_lab_id,
                    "source": "linked",
                }
            return None

        safe_lab_id = association["labId"]
        source = _association_source(association.get("source"))
        if source == "linked":
            if not self._remove_link_files(safe_lab_id):
                return None
            return {
                "deleted": True,
                "unlinked": True,
                "labId": safe_lab_id,
                "source": source,
            }

        deletion = await self.delete_resources(
            shell_ids=association.get("shellIds") or [],
            submodel_ids=association.get("submodelIds") or [],
        )
        if not isinstance(deletion, dict):
            return {"error": "BaSyx resource deletion failed"}
        if deletion.get("error"):
            return deletion
        self.package_catalog.delete(safe_lab_id)
        return {
            "deleted": True,
            "labId": safe_lab_id,
            "source": source,
            "deletedAasIds": deletion.get("deletedAasIds", []),
            "deletedSubmodelIds": deletion.get("deletedSubmodelIds", []),
        }


__all__ = ["AasAssociationService"]
