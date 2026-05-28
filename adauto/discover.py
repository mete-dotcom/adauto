"""mDNS discovery for adauto — adauto.local + adauto-<hostname>.local"""
from __future__ import annotations

import socket
from typing import Optional

SERVICE_TYPE = "_adauto._tcp.local."
DEFAULT_PORT = 8766


def _hostname() -> str:
    return socket.gethostname().lower().replace(" ", "-")


def start_beacon(port: int = DEFAULT_PORT) -> Optional[object]:
    """
    Broadcast adauto on the local network.
    Returns the ServiceInfo object (keep reference to keep it alive) or None.
    """
    try:
        from zeroconf import ServiceInfo, Zeroconf
    except ImportError:
        return None

    hostname = _hostname()
    primary   = f"adauto.{SERVICE_TYPE}"
    secondary = f"adauto-{hostname}.{SERVICE_TYPE}"

    ip = socket.gethostbyname(socket.gethostname())
    ip_bytes = socket.inet_aton(ip)

    infos = []
    zc = Zeroconf()
    for name in (primary, secondary):
        info = ServiceInfo(
            SERVICE_TYPE,
            name,
            addresses=[ip_bytes],
            port=port,
            properties={
                b"version": b"0.1.0",
                b"product": b"adauto",
            },
            server=f"{hostname}.local.",
        )
        try:
            zc.register_service(info)
            infos.append(info)
        except Exception:
            pass

    return (zc, infos)  # caller must hold reference


def discover(timeout: float = 3.0) -> list[dict]:
    """
    Find all adauto instances on the local network.
    Returns list of {name, host, port, properties}.
    """
    try:
        from zeroconf import ServiceBrowser, Zeroconf
    except ImportError:
        return []

    found = []

    class _Listener:
        def add_service(self, zc, stype, name):
            info = zc.get_service_info(stype, name)
            if info:
                found.append({
                    "name": name,
                    "host": socket.inet_ntoa(info.addresses[0]) if info.addresses else "?",
                    "port": info.port,
                    "properties": {k.decode(): v.decode() for k, v in info.properties.items()},
                })
        def remove_service(self, *_): pass
        def update_service(self, *_): pass

    zc = Zeroconf()
    browser = ServiceBrowser(zc, SERVICE_TYPE, _Listener())
    import time
    time.sleep(timeout)
    zc.close()
    return found
