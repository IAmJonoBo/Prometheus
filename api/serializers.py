"""Utility functions for converting pipeline dataclasses to JSON."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime
from typing import Any


def to_serialisable(obj: Any) -> Any:
    """Recursively convert dataclasses and nested objects to JSON-friendly types."""

    if is_dataclass(obj):
        payload = {}
        for field_ in fields(obj):
            payload[field_.name] = to_serialisable(getattr(obj, field_.name))
        return payload
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {key: to_serialisable(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_serialisable(item) for item in obj]
    return obj
