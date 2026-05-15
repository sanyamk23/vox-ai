"""
Shared utilities for the chat application.
Consolidates repeated logic (DRY principle).
"""
import logging
from urllib.parse import unquote, parse_qs

logger = logging.getLogger("vox")


def parse_query_params(scope: dict) -> dict:
    """
    Extract and decode query parameters from a WebSocket scope.
    Replaces the duplicated manual parsing in every consumer.
    """
    raw = scope.get("query_string", b"").decode()
    parsed = parse_qs(raw)
    return {
        "jd": unquote(parsed.get("jd", [None])[0] or ""),
        "name": unquote(parsed.get("name", ["Candidate"])[0] or "Candidate"),
        "company": unquote(parsed.get("company", [""])[0] or ""),
    }
