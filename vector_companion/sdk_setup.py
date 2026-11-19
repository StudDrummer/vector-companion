"""Configure the Vector Python SDK automatically from wire-pod (no prompts).

Same steps as `python -m anki_vector.configure`: download the robot's certificate
from wire-pod, ask Vector for an SDK token (guid), write ~/.anki_vector/sdk_config.ini.
"""
from __future__ import annotations

import configparser
import json
import os
import urllib.request
from pathlib import Path

ANKI_DIR = Path.home() / ".anki_vector"
CONFIG = ANKI_DIR / "sdk_config.ini"
WIREPOD_TOKEN = "2vMhFgktH3Jrbemm2WHkfGN"  # the fixed session id wire-pod's configure script uses


def _get(url: str, timeout: float = 5) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def robot_info(wirepod: str) -> dict:
    info = json.loads(_get(f"{wirepod}/api-sdk/get_sdk_info"))
    bots = info.get("robots") or []
    if not bots:
        raise RuntimeError("wire-pod has no robot set up yet")
    return bots[0]


def is_configured(serial: str) -> bool:
    if not CONFIG.exists():
        return False
    c = configparser.ConfigParser(strict=False)
    c.read(CONFIG)
    return serial in c and all(k in c[serial] for k in ("cert", "ip", "name", "guid")) \
        and Path(c[serial]["cert"]).exists()


def update_ip(serial: str, ip: str) -> None:
    c = configparser.ConfigParser(strict=False)
    c.read(CONFIG)
    if serial in c and c[serial].get("ip") != ip:
        c[serial]["ip"] = ip
        with open(CONFIG, "w") as f:
            c.write(f)


def ensure_config(wirepod: str = "http://127.0.0.1:8080") -> str:
    """Return the robot serial, configuring the SDK first if needed."""
    bot = robot_info(wirepod)
    serial, ip = bot["esn"], bot["ip_address"]
    if is_configured(serial):
        update_ip(serial, ip)  # Vector's IP can change after a router restart
        return serial
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    from anki_vector.configure.__main__ import user_authentication, write_config

    cert = _get(f"{wirepod}/session-certs/{serial}")
    parsed = x509.load_pem_x509_certificate(cert, default_backend())
    name = next(a.value for a in parsed.subject if a.oid.dotted_string == "2.5.4.3")  # CN, e.g. Vector-A1B2
    ANKI_DIR.mkdir(exist_ok=True)
    cert_file = ANKI_DIR / f"{name}-{serial}.cert"
    with os.fdopen(os.open(cert_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as f:
        f.write(cert)
    guid = user_authentication(WIREPOD_TOKEN, cert, ip, name)
    write_config(serial, str(cert_file), ip, name, guid)
    return serial


if __name__ == "__main__":
    print("configured", ensure_config(os.environ.get("WIREPOD_URL", "http://127.0.0.1:8080")))
