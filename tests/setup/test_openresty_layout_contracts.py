import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OPENRESTY_ROOT = ROOT / "openresty"


def test_openresty_uses_the_canonical_gateway_layout():
    gateway = OPENRESTY_ROOT / "gateway.conf"
    fragments = sorted(OPENRESTY_ROOT.joinpath("conf.d").glob("gateway_*.conf"))
    legacy_files = list(OPENRESTY_ROOT.glob("lab_access*.conf"))
    dockerfile = (OPENRESTY_ROOT / "Dockerfile").read_text(encoding="utf-8")
    gateway_config = gateway.read_text(encoding="utf-8")
    nginx_config = (OPENRESTY_ROOT / "nginx.conf").read_text(encoding="utf-8")

    assert gateway.is_file()
    assert len(fragments) == 23
    assert not legacy_files

    expected_names = {path.name for path in fragments}
    included_names = set(
        re.findall(
            r"(?m)^\s*include /etc/openresty/conf\.d/(gateway_[A-Za-z0-9_-]+\.conf);",
            gateway_config,
        )
    )
    copied_names = set(
        re.findall(r"(?m)^COPY conf\.d/(gateway_[A-Za-z0-9_-]+\.conf) ", dockerfile)
    )

    assert expected_names == included_names == copied_names
    assert "include /etc/openresty/gateway.conf;" in nginx_config
