"""Helpers for safe, user-facing execution summaries."""

from __future__ import annotations

from typing import Any


def add_trace(state: dict[str, Any], agent: str, event: str, detail: str) -> list[dict[str, str]]:
    """Append a status summary without exposing private model reasoning."""
    trace = list(state.get("trace", []))
    trace.append({"agent": agent, "event": event, "detail": detail})
    return trace
