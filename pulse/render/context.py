"""Inputs shared by every panel renderer."""

from __future__ import annotations

from dataclasses import dataclass

from pulse.config import Profile
from pulse.models import Snapshot
from pulse.render.theme import Theme


@dataclass(frozen=True)
class RenderContext:
    snapshot: Snapshot
    profile: Profile
    theme: Theme
