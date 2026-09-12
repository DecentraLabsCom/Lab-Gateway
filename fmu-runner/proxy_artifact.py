"""Pure assembly helpers for reservation-scoped FMU proxy artifacts."""

from collections.abc import Iterable, Mapping
from hashlib import sha256
import hmac
import io
import json
from pathlib import Path
import zipfile
from typing import Any


RuntimeFile = tuple[Path, str]


def build_proxy_artifact(
    *,
    model_xml: bytes,
    config_payload: Mapping[str, Any],
    runtime_files: Iterable[RuntimeFile],
) -> bytes:
    """Build the proxy archive with the established FMI runtime layout."""
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("modelDescription.xml", model_xml)
        # The native runtime receives fmuResourceLocation pointing to resources/.
        archive.writestr("resources/modelDescription.xml", model_xml)
        archive.writestr(
            "resources/config.json",
            json.dumps(config_payload, separators=(",", ":")),
        )
        for file_path, archive_name in runtime_files:
            archive.write(file_path, archive_name)
    return archive_buffer.getvalue()


def build_proxy_artifact_headers(
    *,
    artifact_bytes: bytes,
    lab_id: str,
    signing_key: str,
) -> dict[str, str]:
    """Build the download headers for a generated proxy artifact."""
    artifact_sha256 = sha256(artifact_bytes).hexdigest()
    headers = {
        "Content-Disposition": f'attachment; filename="fmu-proxy-lab-{lab_id}.fmu"',
        "X-Proxy-Artifact-Sha256": artifact_sha256,
    }
    if signing_key:
        signature = hmac.new(
            signing_key.encode("utf-8"),
            artifact_bytes,
            sha256,
        ).hexdigest()
        headers["X-Proxy-Artifact-Signature"] = f"hmac-sha256={signature}"
    return headers
