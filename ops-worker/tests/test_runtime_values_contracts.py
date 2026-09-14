import re

import runtime_values
import worker


def test_runtime_values_contract_preserves_static_defaults_and_patterns():
    assert runtime_values.DEFAULT_LABSTATION_EXE == r"C:\LabStation\LabStation.exe"
    assert runtime_values.WINRM_PORT == 5986
    assert runtime_values.WINRM_TRUST_CERTIFICATE_NAME == "server.cer"
    assert runtime_values.WINRM_TRUST_PEM_NAME == "server.pem"
    assert runtime_values.WINRM_TRUST_METADATA_NAME == "metadata.json"
    assert runtime_values.WINRM_CERTIFICATE_EXTENSIONS == {".cer", ".crt", ".der", ".pem"}
    assert runtime_values.ENOUGH_DISCOVERY_SIGNALS == {
        "labstation-detected",
        "winrm-reachable",
    }
    assert runtime_values.HTTP_HEADER_NAME_RE.fullmatch("X-Ops-Internal-Token")
    assert runtime_values.HOST_NAME_RE.fullmatch("lab-ws-01")
    assert runtime_values.WINRM_TRUST_REF_RE.fullmatch("lab-ws-01")
    assert runtime_values.GUAC_SELECTOR_RE.fullmatch("guac:id:42")
    assert not runtime_values.GUAC_SELECTOR_RE.fullmatch("guac:id:0")


def test_worker_reexports_runtime_values_without_changing_patch_points():
    for name in runtime_values.RUNTIME_VALUE_NAMES:
        assert getattr(worker, name) is getattr(runtime_values, name)

    assert isinstance(worker.GUAC_SELECTOR_RE, type(re.compile("")))

