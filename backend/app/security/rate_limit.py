from __future__ import annotations

from collections.abc import Callable

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


def client_ip(request: Request) -> str:
    return get_remote_address(request)
