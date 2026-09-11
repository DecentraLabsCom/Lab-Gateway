import json
import logging
import os
from pathlib import Path
from typing import Optional

import aiosqlite


async def init_history_db(db_path: str | Path) -> None:
    """Create or migrate the simulation history schema."""
    database_path = str(db_path)
    os.makedirs(os.path.dirname(database_path) or ".", exist_ok=True)
    async with aiosqlite.connect(database_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS simulation_history (
                id TEXT PRIMARY KEY,
                lab_id TEXT NOT NULL,
                user_sub TEXT,
                reservation_key TEXT,
                puc_hash TEXT,
                credential_hash TEXT,
                fmu_filename TEXT,
                fmi_type TEXT DEFAULT 'CoSimulation',
                parameters TEXT,
                options TEXT,
                result TEXT,
                elapsed_seconds REAL,
                status TEXT DEFAULT 'completed',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        cursor = await db.execute("PRAGMA table_info(simulation_history)")
        columns = {row[1] for row in await cursor.fetchall()}
        for name in ("reservation_key", "puc_hash", "credential_hash"):
            if name not in columns:
                await db.execute(f"ALTER TABLE simulation_history ADD COLUMN {name} TEXT")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_history_lab ON simulation_history(lab_id)")
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_history_reservation ON simulation_history(lab_id, reservation_key)"
        )
        await db.commit()


async def save_history(
    db_path: str | Path,
    *,
    sim_id,
    lab_id,
    claims,
    fmu_filename,
    fmi_type,
    params,
    options,
    result,
    elapsed,
    logger: logging.Logger,
) -> None:
    """Persist a completed simulation without affecting the response path."""
    try:
        async with aiosqlite.connect(str(db_path)) as db:
            await db.execute(
                "INSERT INTO simulation_history "
                "(id,lab_id,user_sub,reservation_key,puc_hash,credential_hash,fmu_filename,fmi_type,parameters,options,result,elapsed_seconds) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    sim_id,
                    str(lab_id),
                    claims.get("sub"),
                    claims.get("reservationKey"),
                    claims.get("pucHash"),
                    claims.get("_credentialHash"),
                    fmu_filename,
                    fmi_type,
                    json.dumps(params),
                    json.dumps(options),
                    json.dumps(result),
                    elapsed,
                ),
            )
            await db.commit()
    except Exception as exc:
        logger.error("Failed to save simulation history: %s", exc)


async def list_history(
    db_path: str | Path,
    *,
    lab_id: str,
    reservation_key: str,
    puc_hash: str,
    limit: int,
    offset: int,
) -> list[dict]:
    """Return history rows scoped to the authorized lab and pseudonymous user."""
    async with aiosqlite.connect(str(db_path)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, lab_id, user_sub, fmu_filename, fmi_type, elapsed_seconds, status, created_at "
            "FROM simulation_history WHERE lab_id = ? AND lower(reservation_key) = ? AND lower(puc_hash) = ? "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (lab_id, reservation_key, puc_hash, limit, offset),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_history_result(
    db_path: str | Path,
    *,
    sim_id: str,
    lab_id: str,
    reservation_key: str,
    puc_hash: str,
) -> Optional[dict]:
    """Return one history row when it belongs to the requested authorization scope."""
    async with aiosqlite.connect(str(db_path)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM simulation_history WHERE id = ? AND lab_id = ? AND lower(reservation_key) = ? AND lower(puc_hash) = ?",
            (sim_id, lab_id, reservation_key, puc_hash),
        )
        row = await cursor.fetchone()
    return dict(row) if row else None