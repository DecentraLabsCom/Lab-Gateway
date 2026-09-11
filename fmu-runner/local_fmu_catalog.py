from pathlib import Path

from fastapi import HTTPException


def _local_backend_health_payload(*, data_path: str | Path, executor) -> dict:
    checks = {"fmuDataPath": False, "executor": False}
    base = Path(data_path)
    checks["fmuDataPath"] = base.is_dir()
    fmu_count = sum(1 for _ in base.rglob("*.fmu")) if checks["fmuDataPath"] else 0
    try:
        checks["executor"] = (
            executor is not None
            and (not executor._broken if hasattr(executor, "_broken") else True)
        )
    except Exception:
        checks["executor"] = False
    overall = all(checks.values())
    return {
        "status": "UP" if overall else "DEGRADED",
        "checks": checks,
        "fmuCount": fmu_count,
        "backendMode": "local",
    }


def _load_local_model_metadata(
    fmu_filename: str,
    *,
    resolve_fmu_path,
    model_description_reader,
    model_metadata_builder,
    logger,
) -> dict:
    fmu_path = resolve_fmu_path(fmu_filename)
    try:
        model_description = model_description_reader(str(fmu_path))
    except Exception as exc:
        logger.error("Failed to read model description for %s: %s", fmu_filename, exc)
        raise HTTPException(status_code=422, detail="Cannot parse FMU") from exc
    return model_metadata_builder(model_description)


def _list_local_fmus_payload(
    claimed_file: str,
    *,
    data_path: str | Path,
    resolve_fmu_path,
    is_within_base,
) -> dict:
    resolved = resolve_fmu_path(claimed_file)
    base = Path(data_path).resolve()
    if not is_within_base(base, resolved):
        return {"fmus": []}
    relative_path = resolved.relative_to(base)
    return {
        "fmus": [{
            "filename": resolved.name,
            "path": str(relative_path),
            "sizeBytes": resolved.stat().st_size,
            "source": "provisioned",
        }]
    }