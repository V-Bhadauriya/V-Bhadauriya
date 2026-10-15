"""Anonymisation of private repositories.

Private repository names are replaced at ingestion time so they never reach
the snapshot, the fixtures, or any rendered asset.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

PRIVATE_PREFIX = "private/workload-"


def build_alias_map(private_names: Iterable[str]) -> dict[str, str]:
    """Map each distinct private repo name to a stable, meaningless alias."""
    unique = list(dict.fromkeys(private_names))
    return {name: f"{PRIVATE_PREFIX}{index:02d}" for index, name in enumerate(unique, start=1)}


def alias(name: str, is_private: bool, aliases: Mapping[str, str]) -> str:
    if not is_private:
        return name
    # An unknown private name must never leak: fall back to a generic alias.
    return aliases.get(name, f"{PRIVATE_PREFIX}00")


def is_anonymised(name: str) -> bool:
    return name.startswith(PRIVATE_PREFIX)
