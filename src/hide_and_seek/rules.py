"""Gameplay rules for stop and route eligibility."""

from __future__ import annotations

from collections.abc import Iterable


PLAY_START_HOUR = 9
PLAY_END_HOUR = 18
MIN_TOTAL_EVENTS = 50


def is_time_in_window(gtfs_time: str) -> bool:
    """Return whether a GTFS time falls inside the gameplay window.

    Args:
        gtfs_time: Time string like ``HH:MM:SS``.

    Returns:
        True when the hour is within 09:00 <= t < 18:00.
    """
    hour = int(gtfs_time.split(":", 1)[0])
    return PLAY_START_HOUR <= hour < PLAY_END_HOUR


def is_stop_eligible(event_count: int) -> bool:
    """Return whether a stop passes the gameplay frequency rule."""
    return event_count >= MIN_TOTAL_EVENTS


def has_consecutive_eligible_stops(
    stop_ids: Iterable[str], eligible_stop_ids: set[str]
) -> bool:
    """Return whether a trip sequence contains two eligible consecutive stops."""
    previous_eligible = False
    for stop_id in stop_ids:
        current_eligible = stop_id in eligible_stop_ids
        if previous_eligible and current_eligible:
            return True
        previous_eligible = current_eligible
    return False
