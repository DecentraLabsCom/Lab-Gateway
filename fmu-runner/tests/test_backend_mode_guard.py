def test_local_backend_requires_explicit_development_switch(monkeypatch):
    import runner_application as application

    monkeypatch.setattr(application, "FMU_BACKEND_MODE", "local")
    monkeypatch.setattr(application, "FMU_LOCAL_DEV_MODE", False)

    backend = application._build_fmu_backend()

    assert backend.mode == "local"
    assert backend.supports_local_execution is False


def test_local_backend_is_enabled_only_with_explicit_development_switch(monkeypatch):
    import runner_application as application

    monkeypatch.setattr(application, "FMU_BACKEND_MODE", "local")
    monkeypatch.setattr(application, "FMU_LOCAL_DEV_MODE", True)

    backend = application._build_fmu_backend()

    assert backend.supports_local_execution is True


def test_backend_factory_preserves_main_backend_class_patch_point(monkeypatch):
    import runner_application as application

    class _PatchedLocalBackend:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(application, "FMU_BACKEND_MODE", "local")
    monkeypatch.setattr(application, "FMU_LOCAL_DEV_MODE", True)
    monkeypatch.setattr(application, "LocalFmuBackend", _PatchedLocalBackend)

    backend = application._build_fmu_backend()

    assert isinstance(backend, _PatchedLocalBackend)
    assert backend.kwargs["allow_execution"] is True
