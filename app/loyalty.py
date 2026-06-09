"""Helpers for loading and interpreting the loyalty JSON configuration."""

from __future__ import annotations

import json
import os
from typing import Any


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """Load and return the loyalty configuration JSON."""
    if config_path is None:
        config_path = os.environ.get("LOYALTY_CONFIG_PATH", "config/pizzeria.json")
    with open(config_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def get_status_message(config: dict, points: int) -> str:
    """Return the human-readable loyalty status shown on wallet passes."""
    rewards = config.get("rewards", [])
    if not rewards:
        return f"{points} point{'s' if points != 1 else ''}"

    reward = rewards[0]  # primary reward drives the status message
    points_required: int = reward["points_required"]

    if points >= points_required:
        return f"Reward available! You have {points} point{'s' if points != 1 else ''}."

    remaining = points_required - points
    template: str = reward.get("status_template", "{remaining} points left!")
    return template.format(
        remaining=remaining,
        points=points,
        points_required=points_required,
    )


def get_progress_pct(config: dict, points: int) -> int:
    """Return 0-100 progress toward the next reward."""
    rewards = config.get("rewards", [])
    if not rewards:
        return 0
    points_required: int = rewards[0]["points_required"]
    return min(100, int(points / points_required * 100))
