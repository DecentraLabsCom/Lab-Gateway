import shutil
from pathlib import Path


def cleanup_fmu_temp_files(temp_dir: Path) -> int:
    removed = 0
    for entry in temp_dir.iterdir():
        if entry.is_dir() and entry.name.startswith("tmp") and (entry / "modelDescription.xml").exists():
            try:
                shutil.rmtree(entry)
                removed += 1
            except Exception:
                pass
    return removed