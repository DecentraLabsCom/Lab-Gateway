"""Repository-level guards for the Gateway modularization baseline."""

import ast
import importlib
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OPS_WORKER_ROOT = ROOT / "ops-worker"
OPENRESTY_ROOT = ROOT / "openresty"
GATEWAY_WORKFLOW = ROOT / ".github" / "workflows" / "gateway-tests.yml"
STANDALONE_COMMAND_FILES = (
    ROOT / "blockchain-services" / "docker-compose.yml",
    ROOT / "blockchain-services" / "test-wallet-local.sh",
    ROOT / "blockchain-services" / "test-wallet-local.ps1",
)

def _worker_module():
    worker_path = str(OPS_WORKER_ROOT)
    if worker_path not in sys.path:
        sys.path.insert(0, worker_path)
    return importlib.import_module("worker")


def _blueprint_definitions() -> dict[str, list[str]]:
    definitions: dict[str, list[str]] = {}
    for path in OPS_WORKER_ROOT.rglob("*.py"):
        relative = path.relative_to(OPS_WORKER_ROOT)
        if "tests" in relative.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            is_blueprint = isinstance(function, ast.Name) and function.id == "Blueprint"
            is_blueprint = is_blueprint or (
                isinstance(function, ast.Attribute) and function.attr == "Blueprint"
            )
            if not is_blueprint or not node.args:
                continue
            name = node.args[0]
            if isinstance(name, ast.Constant) and isinstance(name.value, str):
                definitions.setdefault(name.value, []).append(str(relative))
    return definitions


def test_registered_routes_have_no_duplicate_path_method_pairs():
    worker = _worker_module()
    route_keys = [
        (rule.rule, method)
        for rule in worker.APP.url_map.iter_rules()
        for method in rule.methods - {"HEAD", "OPTIONS"}
    ]

    duplicates = sorted(
        key for key, count in Counter(route_keys).items() if count > 1
    )
    assert not duplicates, f"duplicate Flask route registrations: {duplicates}"


def test_every_source_blueprint_is_registered_exactly_once():
    worker = _worker_module()
    definitions = _blueprint_definitions()
    registered = set(worker.APP.blueprints)

    duplicate_definitions = {
        name: paths for name, paths in definitions.items() if len(paths) != 1
    }
    assert not duplicate_definitions, (
        "Blueprint names must have one source definition: "
        f"{duplicate_definitions}"
    )
    assert registered == set(definitions), {
        "registered_without_source": sorted(registered - set(definitions)),
        "source_without_registration": sorted(set(definitions) - registered),
    }


class _TopLevelCallVisitor(ast.NodeVisitor):
    """Collect calls executed while importing a composable module."""

    def visit_FunctionDef(self, node):  # noqa: N802 - ast visitor API
        return

    def visit_AsyncFunctionDef(self, node):  # noqa: N802 - ast visitor API
        return

    def visit_ClassDef(self, node):  # noqa: N802 - ast visitor API
        return

    def visit_Lambda(self, node):  # noqa: N802 - ast visitor API
        return

    def visit_Call(self, node):  # noqa: N802 - ast visitor API
        self.calls.add(self._call_name(node.func))
        self.generic_visit(node)

    def __init__(self):
        self.calls: set[str] = set()

    @staticmethod
    def _call_name(node) -> str:
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
        return ".".join(reversed(parts))


COMPOSABLE_SUFFIXES = (
    "_blueprint.py",
    "_context.py",
    "_factory.py",
    "_route.py",
    "_routes.py",
    "_runtime.py",
    "_service.py",
    "_values.py",
)
IMPORT_TIME_SIDE_EFFECTS = {
    "BackgroundScheduler",
    "Process",
    "Thread",
    "connect",
    "create_connection",
    "create_engine",
    "getaddrinfo",
    "os.remove",
    "os.system",
    "os.unlink",
    "Popen",
    "requests.delete",
    "requests.get",
    "requests.post",
    "requests.put",
    "send_magic_packet",
    "serve",
    "sleep",
    "subprocess.run",
    "time.sleep",
}


def test_composable_ops_worker_modules_do_not_run_external_work_at_import():
    violations = {}
    for path in OPS_WORKER_ROOT.glob("*.py"):
        if path.name == "worker.py" or not path.name.endswith(COMPOSABLE_SUFFIXES):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = _TopLevelCallVisitor()
        visitor.visit(tree)
        matches = sorted(visitor.calls & IMPORT_TIME_SIDE_EFFECTS)
        if matches:
            violations[str(path.relative_to(OPS_WORKER_ROOT))] = matches

    assert not violations, (
        "composable modules must defer external work until an explicit call: "
        f"{violations}"
    )


def test_every_openresty_access_fragment_is_included_and_packaged():
    access_conf = (OPENRESTY_ROOT / "gateway.conf").read_text(encoding="utf-8")
    dockerfile = (OPENRESTY_ROOT / "Dockerfile").read_text(encoding="utf-8")
    fragments = {path.name for path in OPENRESTY_ROOT.glob("lab_access_*.conf")}
    included = set(
        re.findall(
            r"(?m)^\s*include /etc/openresty/(lab_access_[A-Za-z0-9_-]+\.conf);",
            access_conf,
        )
    )
    copied = set(
        re.findall(r"(?m)^COPY (lab_access_[A-Za-z0-9_-]+\.conf) ", dockerfile)
    )

    assert fragments == included == copied, {
        "files_without_include": sorted(fragments - included),
        "includes_without_file": sorted(included - fragments),
        "files_without_docker_copy": sorted(fragments - copied),
        "docker_copies_without_file": sorted(copied - fragments),
    }


def test_ci_runs_gateway_topology_contracts_for_full_lite_and_standalone():
    workflow = GATEWAY_WORKFLOW.read_text(encoding="utf-8")

    assert "python -m pytest tests/setup -q" in workflow
    assert "verify-gateway-topologies.sh" in workflow
    for topology in ("Full", "Lite", "standalone"):
        assert topology in workflow


def test_standalone_guidance_uses_the_supported_compose_cli():
    for path in STANDALONE_COMMAND_FILES:
        content = path.read_text(encoding="utf-8")
        assert not re.search(r"\bdocker-compose\s+up\b", content), path
