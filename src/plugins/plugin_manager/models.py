from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, cast

type PluginState = Literal["enabled", "disabled"]
VALID_STATES: set[PluginState] = {"enabled", "disabled"}


@dataclass(slots=True)
class PluginSwitch:
    default: PluginState = "enabled"
    global_state: PluginState | None = None
    groups: dict[str, dict[str, PluginState]] = field(default_factory=dict)
    users: dict[str, dict[str, PluginState]] = field(default_factory=dict)


@dataclass(slots=True)
class SwitchConfig:
    plugins: dict[str, PluginSwitch] = field(default_factory=dict)


def normalize_state(value: object, *, field_name: str) -> PluginState:
    if value is None:
        return "enabled"
    if value not in VALID_STATES:
        raise ValueError(f"{field_name} must be one of: enabled, disabled")
    return cast("PluginState", value)
