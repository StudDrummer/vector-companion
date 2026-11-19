"""Configure the Vector Python SDK automatically (no prompts).

Writes ~/.anki_vector/sdk_config.ini + the robot's certificate, like
`python -m anki_vector.configure`, but without any questions:

  * certificate: from wire-pod (/session-certs/<esn>) if it saved one, otherwise read
    straight from Vector's TLS port (it's the same certificate the SDK pins);
  * robot name: from the certificate (Vector-XXXX);
  * guid (SDK access token): from wire-pod's robot info, otherwise requested from Vector.
"""
from __future__ import annotations

import configparser
import json
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path

ANKI_DIR = Path.home() / ".anki_vector"
CONFIG = ANKI_DIR / "sdk_config.ini"
WIREPOD_TOKEN = "2vMhFgktH3Jrbemm2WHkfGN"  # the public session id wire-pod's own configure script uses


def _get(url: str, timeout: float = 5) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def sdk_info(wirepod: str) -> dict:
    return json.loads(_get(f"{wirepod}/api-sdk/get_sdk_info"))


def is_configured(serial: str) -> bool:
    if not CONFIG.exists():
        return False
    c = configparser.ConfigParser(strict=False)
    c.read(CONFIG)
    sec = next((c[s] for s in c.sections() if s.lower() == serial.lower()), None)
    return bool(sec) and all(sec.get(k) for k in ("cert", "ip", "name", "guid")) and Path(sec["cert"]).exists()


def update_ip(serial: str, ip: str) -> None:
    c = configparser.ConfigParser(strict=False)
    c.read(CONFIG)
    for s in c.sections():
        if s.lower() == serial.lower() and c[s].get("ip") != ip:
            c[s]["ip"] = ip
            with open(CONFIG, "w") as f:
                c.write(f)


def fetch_cert(wirepod: str, serial: str, ip: str) -> bytes:
    try:
        return _get(f"{wirepod}/session-certs/{serial}")
    except urllib.error.HTTPError:
        pass  # wire-pod didn't save one: ask Vector directly
    pem = ssl.get_server_certificate((ip, 443), timeout=10)
    return pem.encode()


def cert_name(cert: bytes) -> str:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    c = x509.load_pem_x509_certificate(cert)
    for part in (c.issuer, c.subject):  # wire-pod reads the issuer CN; fall back to subject
        cn = part.get_attributes_for_oid(NameOID.COMMON_NAME)
        if cn and str(cn[0].value).startswith("Vector-"):
            return str(cn[0].value)
    raise RuntimeError("couldn't find Vector's name in his certificate")


def write_config(serial: str, cert_file: Path, ip: str, name: str, guid: str) -> None:
    ANKI_DIR.mkdir(exist_ok=True)
    c = configparser.ConfigParser(strict=False)
    if CONFIG.exists():
        c.read(CONFIG)
    c[serial] = {"cert": str(cert_file), "ip": ip, "name": name, "guid": guid}
    with os.fdopen(os.open(CONFIG, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        c.write(f)


def ensure_config(wirepod: str = "http://127.0.0.1:8080") -> str:
    """Return the robot serial, configuring the SDK first if needed."""
    info = sdk_info(wirepod)
    bots = info.get("robots") or []
    if not bots:
        raise RuntimeError("wire-pod has no robot set up yet")
    bot = bots[0]
    serial, ip = bot["esn"], bot["ip_address"]
    if is_configured(serial):
        update_ip(serial, ip)  # Vector's IP can change after a router restart
        return serial
    cert = fetch_cert(wirepod, serial, ip)
    name = cert_name(cert)
    ANKI_DIR.mkdir(exist_ok=True)
    cert_file = ANKI_DIR / f"{name}-{serial}.cert"
    with os.fdopen(os.open(cert_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as f:
        f.write(cert)
    guid = bot.get("guid") or info.get("global_guid")
    if not guid:
        from anki_vector.configure.__main__ import user_authentication
        guid = user_authentication(WIREPOD_TOKEN, cert, ip, name).decode()
    write_config(serial, cert_file, ip, name, guid)
    return serial


if __name__ == "__main__":
    import sys
    try:
        print("   configured robot", ensure_config(os.environ.get("WIREPOD_URL", "http://127.0.0.1:8080")))
    except Exception as e:  # noqa: BLE001
        print(f"   not yet: {e.__class__.__name__}: {e}")
        sys.exit(1)
