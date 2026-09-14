import ast
import re
from pathlib import Path


GATEWAY_ROOT = Path(__file__).resolve().parents[2]
OPS_WORKER_TESTS_ROOT = GATEWAY_ROOT / "ops-worker" / "tests"
WORKER_PATH = GATEWAY_ROOT / "ops-worker" / "worker.py"


def _source_files():
    """Yield repository scripts that can consume the worker entrypoint."""
    suffixes = {".py", ".sh", ".ps1", ".bat"}
    for path in GATEWAY_ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        relative_parts = path.relative_to(GATEWAY_ROOT).parts
        if "__pycache__" in relative_parts or ".git" in relative_parts:
            continue
        # Unit/contract tests import worker to exercise the entrypoint surface;
        # the inventory below is for consumers outside that test suite.
        if path.is_relative_to(OPS_WORKER_TESTS_ROOT):
            continue
        yield path


def _worker_imports(path: Path):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names if alias.name == "worker")
        elif isinstance(node, ast.ImportFrom) and node.module == "worker":
            imports.append("from worker")
    return imports


def _worker_script_import(path: Path) -> bool:
    """Detect shell/PowerShell entrypoint imports without executing them."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    return bool(re.search(r"\b(?:from\s+worker\s+import|import\s+worker)\b", source))


def _worker_member_references(path: Path):
    """Collect worker attributes consumed by the test and script inventory."""
    if path.suffix.lower() != ".py":
        return set()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeError):
        return set()
    return {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "worker"
    }


def _worker_script_member_references(path: Path):
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return set()
    return set(re.findall(r"\bworker\.([A-Za-z_][A-Za-z0-9_]*)", source))


def test_production_code_does_not_import_worker_as_a_dependency():
    production_imports = []
    for path in _source_files():
        relative_parts = path.relative_to(GATEWAY_ROOT).parts
        if path == WORKER_PATH or "tests" in relative_parts:
            continue
        imported = _worker_imports(path) if path.suffix.lower() == ".py" else []
        if imported or _worker_script_import(path):
            production_imports.append(path.relative_to(GATEWAY_ROOT).as_posix())

    assert production_imports == []


def test_worker_consumer_inventory_is_explicitly_test_scoped():
    tests_root = Path(__file__).resolve().parent
    consumer_files = {
        path.name
        for path in tests_root.glob("*.py")
        if "worker" in path.read_text(encoding="utf-8")
    }

    assert "conftest.py" in consumer_files
    assert "test_entrypoint.py" in consumer_files
    assert "test_facade_removal_contracts.py" in consumer_files


def test_worker_script_consumers_are_explicitly_inventoried():
    consumers = {
        path.relative_to(GATEWAY_ROOT).as_posix()
        for path in _source_files()
        if path.suffix.lower() != ".py" and _worker_script_import(path)
    }

    assert consumers == set()


def test_worker_member_references_are_present_on_the_entrypoint_surface():
    import worker

    references = set()
    for path in OPS_WORKER_TESTS_ROOT.glob("*.py"):
        references.update(_worker_member_references(path))
    for path in _source_files():
        if path.suffix.lower() != ".py" and _worker_script_import(path):
            references.update(_worker_script_member_references(path))

    assert references
    assert sorted(name for name in references if not hasattr(worker, name)) == []
