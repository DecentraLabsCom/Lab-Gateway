"""Pure lab-to-Station resolution over live gateway catalogs.

The provider catalog is the source of the ``labId -> accessKey`` relation.
Guacamole is then used to resolve the connection hostname and the registered
host catalog is used only for Station configuration and credentials.
"""

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Dict, List, Optional

from host_inventory_service import find_unique_host_for_connection


def normalize_lab_resource_type(value: Any) -> str:
    """Normalize the provider catalog's physical/FMU resource discriminator."""
    normalized = str(value or "").strip().lower()
    return "fmu" if normalized in {"1", "fmu"} else "lab"


def normalize_fmu_execution_backend(value: Any, default: str = "station") -> str:
    """Normalize the execution location used for FMU operational status."""
    normalized = str(value or "").strip().lower()
    if normalized in {"local", "gateway", "gateway-local", "gateway_local"}:
        return "local"
    if normalized in {"station", "labstation", "lab-station", "remote-station"}:
        return "station"
    fallback = str(default or "station").strip().lower()
    return "local" if fallback in {"local", "gateway", "gateway-local", "gateway_local"} else "station"


def _catalog_value(lab: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = lab.get(key)
        if value is not None and str(value).strip():
            return value
    return None


def extract_lab_catalog(payload: Any) -> List[Dict[str, Any]]:
    """Normalize a backend catalog envelope into valid lab dictionaries."""
    rows = payload
    if isinstance(payload, Mapping):
        rows = payload.get("labs")
    if not isinstance(rows, list):
        return []
    result: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        lab_id = str(row.get("labId") or "").strip()
        if lab_id:
            result.append(dict(row))
    return result


def _lab_index(labs: Sequence[Mapping[str, Any]]) -> Dict[str, Mapping[str, Any]]:
    index: Dict[str, Mapping[str, Any]] = {}
    duplicate_ids = set()
    for lab in labs:
        key = str(lab.get("labId") or "").strip().lower()
        if not key:
            continue
        if key in index:
            duplicate_ids.add(key)
        else:
            index[key] = lab
    for key in duplicate_ids:
        index.pop(key, None)
    return index


def resolve_lab_access_key(
    labs: Sequence[Mapping[str, Any]],
    lab_id: Any,
) -> Optional[str]:
    """Resolve the catalog-owned Guacamole selector for a lab."""
    wanted = str(lab_id or "").strip().lower()
    if not wanted:
        return None
    lab = _lab_index(labs).get(wanted)
    if not lab:
        return None
    access_key = str(lab.get("accessKey") or "").strip()
    return access_key or None


def resolve_lab_resources(
    labs: Sequence[Mapping[str, Any]],
    *,
    default_fmu_backend: str = "station",
) -> List[Dict[str, str]]:
    """Project resource type and FMU execution location for status probes.

    The current provider catalog normally supplies the default backend through
    the Gateway deployment configuration.  The optional catalog fields are
    accepted for future per-resource routing and for installations that expose
    both kinds of FMU explicitly.
    """
    resources: List[Dict[str, str]] = []
    for lab in _lab_index(labs).values():
        lab_id = str(lab.get("labId") or "").strip()
        if lab_id:
            resource = {
                "labId": lab_id,
                "resourceType": normalize_lab_resource_type(lab.get("resourceType")),
            }
            if resource["resourceType"] == "fmu":
                resource["executionBackend"] = normalize_fmu_execution_backend(
                    _catalog_value(lab, (
                        "executionBackend",
                        "fmuBackend",
                        "backendMode",
                        "executionLocation",
                        "hostedOn",
                    )),
                    default_fmu_backend,
                )
                station_host = _catalog_value(lab, (
                    "stationHostName",
                    "stationHost",
                    "executionHost",
                ))
                if station_host is not None:
                    resource["stationHostName"] = str(station_host).strip()
            resources.append(resource)
    return resources


def _connection_for_access_key(
    access_key: str,
    connections: Sequence[Mapping[str, Any]],
    *,
    parse_selector: Callable[[Any], int],
) -> Optional[Dict[str, Any]]:
    try:
        wanted = parse_selector(access_key)
    except (TypeError, ValueError):
        return None
    for connection in connections:
        try:
            connection_id = connection.get("id")
            if not isinstance(connection_id, (str, int)):
                continue
            if int(connection_id) == wanted:
                return dict(connection)
        except (TypeError, ValueError):
            continue
    return None


def resolve_host_for_lab(
    labs: Sequence[Mapping[str, Any]],
    lab_id: Any,
    connections: Sequence[Mapping[str, Any]],
    hosts: Sequence[Dict[str, Any]],
    *,
    parse_selector: Callable[[Any], int],
    normalize_key: Callable[[Any], str],
) -> Optional[Dict[str, Any]]:
    """Resolve one physical lab to the only registered matching host."""
    access_key = resolve_lab_access_key(labs, lab_id)
    if not access_key:
        return None
    connection = _connection_for_access_key(
        access_key,
        connections,
        parse_selector=parse_selector,
    )
    if not connection:
        return None
    return find_unique_host_for_connection(
        list(hosts),
        connection,
        normalize_key=normalize_key,
    )


def resolve_lab_ids_for_host(
    labs: Sequence[Mapping[str, Any]],
    host: Dict[str, Any],
    connections: Sequence[Mapping[str, Any]],
    hosts: Sequence[Dict[str, Any]],
    *,
    parse_selector: Callable[[Any], int],
    normalize_key: Callable[[Any], str],
) -> List[str]:
    """Return catalog lab IDs whose Guacamole connection resolves to ``host``."""
    resolved: List[str] = []
    for lab in _lab_index(labs).values():
        lab_id = str(lab.get("labId") or "").strip()
        mapped_host = resolve_host_for_lab(
            labs,
            lab_id,
            connections,
            hosts,
            parse_selector=parse_selector,
            normalize_key=normalize_key,
        )
        if not mapped_host:
            continue
        if normalize_key(mapped_host.get("name")) == normalize_key(host.get("name")):
            resolved.append(lab_id)
    return resolved


def resolve_lab_associations(
    labs: Sequence[Mapping[str, Any]],
    connections: Sequence[Mapping[str, Any]],
    hosts: Sequence[Dict[str, Any]],
    *,
    parse_selector: Callable[[Any], int],
    normalize_key: Callable[[Any], str],
) -> List[Dict[str, str]]:
    """Project every currently resolvable lab-to-host association."""
    associations: List[Dict[str, str]] = []
    indexed_labs = _lab_index(labs)
    for lab in indexed_labs.values():
        lab_id = str(lab.get("labId") or "").strip()
        host = resolve_host_for_lab(
            labs,
            lab_id,
            connections,
            hosts,
            parse_selector=parse_selector,
            normalize_key=normalize_key,
        )
        host_name = str(host.get("name") or "").strip() if host else ""
        if lab_id and host_name:
            associations.append({"labId": lab_id, "hostName": host_name})
    return associations


def resolve_lab_status_targets(
    labs: Sequence[Mapping[str, Any]],
    connections: Sequence[Mapping[str, Any]],
    hosts: Sequence[Dict[str, Any]],
    *,
    parse_selector: Callable[[Any], int],
    normalize_key: Callable[[Any], str],
) -> List[Dict[str, Any]]:
    """Resolve Guacamole targets, including labs without a Station host.

    The returned records are an internal probe plan.  They deliberately retain
    the connection target only inside the Gateway; the public status projection
    never serializes these records.
    """
    targets: List[Dict[str, Any]] = []
    indexed_labs = _lab_index(labs)
    for lab in indexed_labs.values():
        lab_id = str(lab.get("labId") or "").strip()
        access_key = str(lab.get("accessKey") or "").strip()
        if not lab_id or not access_key:
            continue
        connection = _connection_for_access_key(
            access_key,
            connections,
            parse_selector=parse_selector,
        )
        if not connection:
            continue

        hostname = str(connection.get("hostname") or "").strip()
        if not hostname:
            continue
        target: Dict[str, Any] = {
            "labId": lab_id,
            "connectionId": str(connection.get("id")),
            "hostname": hostname,
            "protocol": str(connection.get("protocol") or "").strip().lower(),
            "port": connection.get("port"),
        }
        host = find_unique_host_for_connection(
            list(hosts),
            connection,
            normalize_key=normalize_key,
        )
        host_name = str(host.get("name") or "").strip() if host else ""
        if host_name:
            target["hostName"] = host_name
        targets.append(target)
    return targets


__all__ = [
    "extract_lab_catalog",
    "normalize_fmu_execution_backend",
    "normalize_lab_resource_type",
    "resolve_lab_associations",
    "resolve_host_for_lab",
    "resolve_lab_access_key",
    "resolve_lab_ids_for_host",
    "resolve_lab_resources",
    "resolve_lab_status_targets",
]
