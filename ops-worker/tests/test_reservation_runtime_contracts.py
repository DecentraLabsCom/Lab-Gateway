from types import SimpleNamespace

from reservation_runtime import create_reservation_orchestrator_class


def _providers(calls):
    import os
    from datetime import datetime, timezone

    return {
        "parse_bool": lambda value, default=False: default,
        "os": os,
        "_env_or_secret_file": lambda name: calls.append(("secret", name)) or "",
        "_parse_reservation_datetime": lambda value: value,
        "_as_utc_datetime": lambda value: value,
        "requests": SimpleNamespace(get=lambda *args, **kwargs: calls.append(("get", args, kwargs))),
        "text": lambda value: value,
        "bindparam": lambda *args, **kwargs: (args, kwargs),
        "handle_reservation_start": lambda payload: calls.append(("start", payload)),
        "handle_reservation_end": lambda payload: calls.append(("end", payload)),
        "record_reservation_operation": lambda *args, **kwargs: calls.append(("record", args, kwargs)),
        "logging": SimpleNamespace(error=lambda *args: calls.append(("error", args))),
        "datetime": datetime,
        "timezone": timezone,
    }


def test_compatibility_class_preserves_two_argument_constructor_and_live_callbacks():
    calls = []
    providers = _providers(calls)
    cls = create_reservation_orchestrator_class(providers)

    orchestrator = cls(None, "registry")

    assert cls.__name__ == "ReservationOrchestrator"
    assert orchestrator.registry == "registry"
    assert orchestrator.engine is None

    providers["parse_bool"] = lambda value, default=False: True
    assert cls(None, "registry-2").enabled is True
