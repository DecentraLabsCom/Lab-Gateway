import ast
from pathlib import Path


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


def test_production_code_does_not_import_worker_as_a_dependency():
    gateway_root = Path(__file__).resolve().parents[2]
    production_imports = []
    for path in gateway_root.rglob("*.py"):
        relative_parts = path.relative_to(gateway_root).parts
        if "tests" in relative_parts or path.name == "worker.py":
            continue
        if _worker_imports(path):
            production_imports.append(path.relative_to(gateway_root).as_posix())

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
    assert "test_legacy_api_contracts.py" in consumer_files
