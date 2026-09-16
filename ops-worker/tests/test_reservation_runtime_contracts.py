from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from reservation_context import ReservationRuntimeContext
from reservation_runtime import create_reservation_orchestrator_class


def _context(calls):
    return ReservationRuntimeContext(
        get_parse_bool=lambda: lambda value, default=False: default,
        get_env=lambda: lambda name, default=None: default,
        get_env_or_secret_file=lambda: lambda name: calls.append(("secret", name)) or "",
        get_parse_reservation_datetime=lambda: lambda value: value,
        get_as_utc_datetime=lambda: lambda value: value,
        get_http_get=lambda: lambda *args, **kwargs: calls.append(("get", args, kwargs)),
        get_sql_text=lambda: lambda value: value,
        get_bindparam=lambda: lambda *args, **kwargs: (args, kwargs),
        get_dispatch_start=lambda: lambda payload: calls.append(("start", payload)),
            get_dispatch_end=lambda: lambda payload: calls.append(("end", payload)),
            get_resolve_host_by_lab=lambda: lambda _lab_id: None,
        get_record_operation=lambda: lambda *args, **kwargs: calls.append(("record", args, kwargs)),
        get_logger=lambda: SimpleNamespace(error=lambda *args: calls.append(("error", args))),
        get_now=lambda: lambda: datetime.now(timezone.utc),
    )


def test_explicit_context_preserves_two_argument_constructor_and_live_callbacks():
    calls = []
    context = _context(calls)
    cls = create_reservation_orchestrator_class(context)

    orchestrator = cls(None, "registry")

    assert cls.__name__ == "ReservationOrchestrator"
    assert orchestrator.registry == "registry"
    assert orchestrator.engine is None

    updated_context = replace(
        context,
        get_parse_bool=lambda: lambda value, default=False: True,
    )
    assert create_reservation_orchestrator_class(updated_context)(None, "registry-2").enabled is True


def test_reservation_context_is_frozen_and_runtime_has_no_provider_namespace():
    context = _context([])

    with pytest.raises(FrozenInstanceError):
        context.get_env = lambda: lambda name, default=None: default

    source = Path(__file__).parents[1].joinpath("reservation_runtime.py").read_text(encoding="utf-8")
    assert "Mapping" not in source
    assert "globals()" not in source
    assert "providers" not in source
