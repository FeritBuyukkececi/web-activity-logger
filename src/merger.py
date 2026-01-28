"""Merge interaction and network logs chronologically, export to JSON file."""

import json
import os
import time

from .utils import extract_root_domain


def create_session(start_url: str) -> dict:
    """
    Initialize a session object.

    Args:
        start_url: The URL where the recording session started.

    Returns:
        A session dict with startTime, startUrl, domain, and empty events list.
    """
    return {
        "session": {
            "startTime": int(time.time() * 1000),
            "endTime": None,
            "startUrl": start_url,
            "domain": extract_root_domain(start_url),
        },
        "events": [],
    }


def add_event(session: dict, event: dict) -> None:
    """
    Add an interaction or network event to the session.

    Args:
        session: The session dict to add the event to.
        event: An event dict with at least 'timestamp' and 'type' keys.
    """
    session["events"].append(event)


def finalize_session(session: dict) -> None:
    """
    Finalize the session by setting end_time and sorting events chronologically.

    Args:
        session: The session dict to finalize.
    """
    # Set end time to current time
    session["session"]["endTime"] = int(time.time() * 1000)

    # Sort events by timestamp
    session["events"].sort(key=lambda e: e.get("timestamp", 0))


def export_session(session: dict, filepath: str) -> None:
    """
    Export the session to a JSON file.

    Creates the parent directory if it doesn't exist.

    Args:
        session: The session dict to export.
        filepath: The path to write the JSON file to.
    """
    # Create parent directory if it doesn't exist
    parent_dir = os.path.dirname(filepath)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    # Write JSON file with pretty formatting
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(session, f, indent=2, ensure_ascii=False)
