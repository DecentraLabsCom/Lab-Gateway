"""Static defaults and validation patterns shared by the Ops Worker composition root."""

import re


DEFAULT_LABSTATION_EXE = r"C:\LabStation\LabStation.exe"
WINRM_PORT = 5986

HTTP_HEADER_NAME_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$")
HOST_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
WINRM_TRUST_REF_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,127}$")
MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}([-:])[0-9A-Fa-f]{2}(\1[0-9A-Fa-f]{2}){4}$")
GUAC_SELECTOR_RE = re.compile(r"^guac:id:([1-9][0-9]*)$")

ENOUGH_DISCOVERY_SIGNALS = {"labstation-detected", "winrm-reachable"}

WINRM_TRUST_CERTIFICATE_NAME = "server.cer"
WINRM_TRUST_PEM_NAME = "server.pem"
WINRM_TRUST_METADATA_NAME = "metadata.json"
WINRM_CERTIFICATE_EXTENSIONS = {".cer", ".crt", ".der", ".pem"}


RUNTIME_VALUE_NAMES = (
    "DEFAULT_LABSTATION_EXE",
    "WINRM_PORT",
    "HTTP_HEADER_NAME_RE",
    "HOST_NAME_RE",
    "WINRM_TRUST_REF_RE",
    "MAC_RE",
    "GUAC_SELECTOR_RE",
    "ENOUGH_DISCOVERY_SIGNALS",
    "WINRM_TRUST_CERTIFICATE_NAME",
    "WINRM_TRUST_PEM_NAME",
    "WINRM_TRUST_METADATA_NAME",
    "WINRM_CERTIFICATE_EXTENSIONS",
)
