import asyncio
from unittest.mock import MagicMock

import aiosqlite

from simulation_history import (
    get_history_result,
    init_history_db,
    list_history,
    save_history,
)


def test_init_history_db_creates_schema_and_indexes(tmp_path):
    db_path = tmp_path / "history.db"

    asyncio.run(init_history_db(db_path))

    async def inspect_schema():
        async with aiosqlite.connect(db_path) as db:
            columns = await db.execute_fetchall("PRAGMA table_info(simulation_history)")
            indexes = await db.execute_fetchall("PRAGMA index_list(simulation_history)")
        return {row[1] for row in columns}, {row[1] for row in indexes}

    columns, indexes = asyncio.run(inspect_schema())
    assert {"id", "lab_id", "reservation_key", "puc_hash", "credential_hash"} <= columns
    assert {"idx_history_lab", "idx_history_reservation"} <= indexes


def test_history_repository_saves_and_filters_by_authorization_scope(tmp_path):
    db_path = tmp_path / "history.db"
    logger = MagicMock()
    claims = {
        "sub": "user-1",
        "reservationKey": "Reservation-1",
        "pucHash": "Puc-1",
        "_credentialHash": "credential-1",
    }
    result = {"outputVariables": [{"name": "y", "value": 2.0}]}

    async def exercise():
        await init_history_db(db_path)
        await save_history(
            db_path,
            sim_id="sim-1",
            lab_id="1",
            claims=claims,
            fmu_filename="model.fmu",
            fmi_type="CoSimulation",
            params={"x": 1.0},
            options={"stopTime": 1.0},
            result=result,
            elapsed=0.25,
            logger=logger,
        )
        rows = await list_history(
            db_path,
            lab_id="1",
            reservation_key="reservation-1",
            puc_hash="puc-1",
            limit=20,
            offset=0,
        )
        stored = await get_history_result(
            db_path,
            sim_id="sim-1",
            lab_id="1",
            reservation_key="reservation-1",
            puc_hash="puc-1",
        )
        return rows, stored

    rows, stored = asyncio.run(exercise())
    assert rows
    assert stored is not None
    assert rows[0]["id"] == "sim-1"
    assert rows[0]["fmu_filename"] == "model.fmu"
    assert stored["result"] == '{"outputVariables": [{"name": "y", "value": 2.0}]}'


def test_history_repository_returns_no_result_for_other_scope(tmp_path):
    db_path = tmp_path / "history.db"

    async def exercise():
        await init_history_db(db_path)
        await save_history(
            db_path,
            sim_id="sim-1",
            lab_id="1",
            claims={"reservationKey": "res-1", "pucHash": "puc-1"},
            fmu_filename="model.fmu",
            fmi_type="CoSimulation",
            params={},
            options={},
            result={},
            elapsed=0.0,
            logger=MagicMock(),
        )
        return await get_history_result(
            db_path,
            sim_id="sim-1",
            lab_id="1",
            reservation_key="res-1",
            puc_hash="other-puc",
        )

    assert asyncio.run(exercise()) is None
