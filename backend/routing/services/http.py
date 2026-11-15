"""Shared HTTP session with retries. One session per thread (we fan out with threads)."""
from __future__ import annotations

import threading

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_local = threading.local()


def get_session() -> requests.Session:
    session = getattr(_local, "session", None)
    if session is None:
        session = requests.Session()
        retry = Retry(
            total=2,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=16)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update(
            {"User-Agent": settings.TRUCK_ROUTING["USER_AGENT"], "Accept": "application/json"}
        )
        _local.session = session
    return session


def timeout() -> float:
    return settings.TRUCK_ROUTING["HTTP_TIMEOUT_SECONDS"]
