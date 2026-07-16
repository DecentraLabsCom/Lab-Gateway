from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TRANSPORT_SOURCES = (
    REPO_ROOT / "fmu-proxy-runtime-src" / "src" / "transport.cpp",
    REPO_ROOT / "fmu-proxy-runtime-src" / "src" / "transport_linux.cpp",
)


def test_native_wss_transport_never_disables_certificate_validation():
    source = "\n".join(path.read_text(encoding="utf-8") for path in TRANSPORT_SOURCES)

    insecure_patterns = (
        "SSL_VERIFY_NONE",
        "CURLOPT_SSL_VERIFYPEER",
        "CURLOPT_SSL_VERIFYHOST",
        "SECURITY_FLAG_IGNORE_UNKNOWN_CA",
        "SECURITY_FLAG_IGNORE_CERT_DATE_INVALID",
        "SECURITY_FLAG_IGNORE_CERT_CN_INVALID",
        "SECURITY_FLAG_IGNORE_CERT_WRONG_USAGE",
        "allow_insecure_tls",
    )

    for pattern in insecure_patterns:
        assert pattern not in source, f"native WSS transport must not contain {pattern}"

    assert "SSL_CTX_set_verify(ssl_context_, SSL_VERIFY_PEER, nullptr)" in source
    assert "SSL_CTX_set_default_verify_paths(ssl_context_)" in source
    assert "SSL_set1_host(ssl_, parsed.host.c_str())" in source
