import shutil
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def cleanup_fmu_temp_files(temp_dir: Path) -> int:
    removed = 0
    for entry in temp_dir.iterdir():
        if entry.is_dir() and entry.name.startswith("tmp") and (entry / "modelDescription.xml").exists():
            try:
                shutil.rmtree(entry)
                removed += 1
            except OSError:
                logger.warning("Unable to remove temporary FMU directory %s", entry, exc_info=True)
    return removed
