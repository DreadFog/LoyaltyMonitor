"""Helpers for loading and interpreting the loyalty JSON configuration."""

from __future__ import annotations

import json
import os
import re
from typing import Any


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """Load and return the loyalty configuration JSON."""
    if config_path is None:
        config_path = os.environ.get("LOYALTY_CONFIG_PATH", "config/pizzeria.json")
    with open(config_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def get_phone_number_extension(config: dict) -> str:
    """Return the configured international phone extension."""
    extension = re.sub(r"\s", "", str(config.get("phone_number_default_extension", "+33")))
    if not re.fullmatch(r"\+\d{1,2}", extension):
        raise ValueError("phone_number_default_extension must start with + and contain 1 or 2 digits.")
    return extension


def normalize_french_phone(value: str, config: dict) -> str | None:
    """Return a French phone number with the configured international extension."""
    compact = re.sub(r"[\s.()-]", "", value.strip())
    if not compact:
        return None

    extension = get_phone_number_extension(config)
    if compact.startswith("0"):
        compact = compact[1:]
    if re.fullmatch(r"[1-9]\d{8}", compact):
        return extension + compact
    if re.fullmatch(re.escape(extension) + r"[1-9]\d{8}", compact):
        return compact
    raise ValueError(
        f"Phone number must contain 9 French digits, optionally prefixed with 0 or {extension}."
    )


def format_phone_number(phone_number: str | None, config: dict) -> str:
    """Group the national portion of a canonical phone number for display."""
    if not phone_number:
        return ""
    try:
        group_size = int(config.get("phone_number_group_size", 2))
    except (TypeError, ValueError):
        group_size = 2
    if group_size < 1:
        group_size = 2

    extension = get_phone_number_extension(config)
    national_number = phone_number[len(extension):] if phone_number.startswith(extension) else phone_number
    first_group_size = len(national_number) % group_size or group_size
    groups = [national_number[:first_group_size]]
    groups.extend(
        national_number[index:index + group_size]
        for index in range(first_group_size, len(national_number), group_size)
    )
    prefix = f"{extension} " if phone_number.startswith(extension) else ""
    return prefix + " ".join(groups)


# ── Track helpers ─────────────────────────────────────────────────────────────

def get_config_tracks(config: dict) -> list[dict]:
    """Return track definitions.

    If the config has an explicit ``tracks`` list, return it.
    Otherwise synthesise a single default track from the first reward.
    """
    tracks = config.get("tracks")
    if tracks:
        return tracks
    rewards = config.get("rewards", [])
    action_unit = rewards[0].get("action_unit", "point") if rewards else "point"
    return [{"id": "default", "name": config.get("program_name", "Loyalty"), "action_unit": action_unit}]


def get_track_points_value(customer, track_id: str) -> int:
    """Return the customer's points for a specific track.

    Falls back to the legacy ``points`` column when no track_points data exists
    (backward-compatible with single-track customers registered before this feature).
    """
    tp = customer.track_points or {}
    if track_id in tp:
        return tp[track_id]
    # legacy: single-track customer, default track maps to points column
    if track_id == "default" and not tp:
        return customer.points
    return 0


def get_track_status(config: dict, track_id: str, points: int) -> dict[str, Any]:
    """Return status info dict for a single track."""
    rewards = [r for r in config.get("rewards", []) if r.get("track_id", "default") == track_id]
    if not rewards:
        return {"message": str(points), "progress_pct": 0, "points_required": 0, "reward": None}

    reward = rewards[0]
    pr: int = reward["points_required"]
    remaining = max(0, pr - points)

    if points >= pr:
        message = reward.get("status_template_complete", "Récompense disponible !")
    else:
        template: str = reward.get("status_template", "{remaining} left!")
        message = template.format(remaining=remaining, points=points, points_required=pr)

    return {
        "message": message,
        "progress_pct": min(100, int(points / pr * 100)) if pr else 0,
        "points_required": pr,
        "reward": reward,
    }


def get_all_track_status(config: dict, customer) -> dict[str, dict]:
    """Return a mapping of track_id → status dict for every configured track."""
    result: dict[str, dict] = {}
    for track in get_config_tracks(config):
        tid = track["id"]
        pts = get_track_points_value(customer, tid)
        ts = get_track_status(config, tid, pts)
        result[tid] = {**ts, "points": pts, "track": track}
    return result


def get_available_rewards(config: dict, customer) -> list[dict]:
    """Return rewards the customer currently has enough points to redeem."""
    available = []
    for reward in config.get("rewards", []):
        track_id = reward.get("track_id", "default")
        if get_track_points_value(customer, track_id) >= reward["points_required"]:
            available.append(reward)
    return available


def get_combined_status_message(config: dict, customer) -> str:
    """Single-line status for wallet passes combining all tracks."""
    all_status = get_all_track_status(config, customer)
    return " • ".join(v["message"] for v in all_status.values())


# ── Legacy single-track helpers (kept for backward compatibility) ─────────────

def get_status_message(config: dict, points: int) -> str:
    """Return the human-readable loyalty status (first reward only)."""
    rewards = config.get("rewards", [])
    if not rewards:
        return f"{points} point{'s' if points != 1 else ''}"
    reward = rewards[0]
    points_required: int = reward["points_required"]
    if points >= points_required:
        return f"Reward available! You have {points} point{'s' if points != 1 else ''}."
    remaining = points_required - points
    template: str = reward.get("status_template", "{remaining} points left!")
    return template.format(remaining=remaining, points=points, points_required=points_required)


def get_progress_pct(config: dict, points: int) -> int:
    """Return 0-100 progress toward the first reward."""
    rewards = config.get("rewards", [])
    if not rewards:
        return 0
    points_required: int = rewards[0]["points_required"]
    return min(100, int(points / points_required * 100))
