"""Network helpers."""

from __future__ import annotations

import socket
from typing import Optional


def get_lan_ip() -> Optional[str]:
    """Return the local LAN IP address if it can be discovered."""

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()
