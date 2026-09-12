"""In-memory host registry used by the Ops Worker routes."""

from typing import Any, Dict, List, Optional


class HostRegistry:
    def __init__(self, cfg: Dict[str, Any]):
        self.hosts: Dict[str, Dict[str, Any]] = {}
        self.lab_index: Dict[str, Dict[str, Any]] = {}
        for host in cfg.get("hosts", []):
            if "name" not in host or "address" not in host:
                continue
            host = dict(host)
            host.pop("winrm_user", None)
            host.pop("winrm_pass", None)
            key = host["name"].lower()
            self.hosts[key] = host
            for lab_id in host.get("labs", []):
                lab_key = str(lab_id).strip().lower()
                if not lab_key:
                    continue
                # Only first mapping wins; if multiple hosts share a lab_id, this will pick the first one.
                self.lab_index.setdefault(lab_key, host)

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        return self.hosts.get(name.lower()) if name else None

    def get_by_lab(self, lab_id: Optional[Any]) -> Optional[Dict[str, Any]]:
        if lab_id is None:
            return None
        return self.lab_index.get(str(lab_id).strip().lower())

    def all_hosts(self) -> List[Dict[str, Any]]:
        return list(self.hosts.values())

    def count(self) -> int:
        return len(self.hosts)
