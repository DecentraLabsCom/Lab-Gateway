"""In-memory host registry used by the Ops Worker routes."""

from typing import Any, Dict, List, Optional


class HostRegistry:
    def __init__(self, cfg: Dict[str, Any]):
        self.hosts: Dict[str, Dict[str, Any]] = {}
        for host in cfg.get("hosts", []):
            if "name" not in host or "address" not in host:
                continue
            host = dict(host)
            host.pop("winrm_user", None)
            host.pop("winrm_pass", None)
            # Lab associations are resolved from the provider catalog. Drop
            # legacy inline mappings at the registry boundary so stale host
            # data cannot become an accidental source of truth again.
            host.pop("labs", None)
            host.pop("validLabIds", None)
            key = host["name"].lower()
            self.hosts[key] = host

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        return self.hosts.get(name.lower()) if name else None

    def all_hosts(self) -> List[Dict[str, Any]]:
        return list(self.hosts.values())

    def count(self) -> int:
        return len(self.hosts)
