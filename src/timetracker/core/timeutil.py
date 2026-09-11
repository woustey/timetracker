"""Timestamp encoding and local-date helpers.

Storage format for instants is ``YYYY-MM-DDTHH:MM:SSZ`` (UTC, second precision).
``local_date_for`` is the single definition of "which calendar day does this
instant belong to" and is what populates ``entry.local_date`` (PRD-02 §4.2).
"""

from __future__ import annotations

import os
import time
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ISO_UTC = "%Y-%m-%dT%H:%M:%SZ"
FALLBACK_TZ = "UTC"


def to_iso_utc(instant: datetime) -> str:
    if instant.tzinfo is None:
        raise ValueError("naive datetime; instants must be timezone-aware")
    return instant.astimezone(UTC).replace(microsecond=0).strftime(ISO_UTC)


def from_iso_utc(text: str) -> datetime:
    return datetime.strptime(text, ISO_UTC).replace(tzinfo=UTC)


def zone(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo(FALLBACK_TZ)


def local_date_for(instant: datetime, tz_name: str) -> date:
    if instant.tzinfo is None:
        raise ValueError("naive datetime; instants must be timezone-aware")
    return instant.astimezone(zone(tz_name)).date()


def local_tz_name() -> str:
    """Best-effort IANA name of the machine's zone, ``UTC`` if undeterminable.

    ``TZ`` is honoured first (it is how tests and CI pin a zone). On POSIX the
    ``/etc/localtime`` symlink usually names the zone. Windows has no IANA name
    at the OS level; ``tzlocal`` would add a fifth dependency, so we fall back
    to UTC there and let the user override in settings (M6).
    """
    env = os.environ.get("TZ")
    if env and _is_valid_zone(env):
        return env
    try:
        target = os.readlink("/etc/localtime")
    except OSError:
        target = ""
    if "zoneinfo/" in target:
        candidate = target.split("zoneinfo/", 1)[1]
        if _is_valid_zone(candidate):
            return candidate
    tzname = time.tzname[0] if time.tzname else ""
    if tzname and _is_valid_zone(tzname):
        return tzname
    return FALLBACK_TZ


def _is_valid_zone(name: str) -> bool:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True
