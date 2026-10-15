"""Marker-based README section rewriting and generated text blocks."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from html import escape

from pulse import metrics
from pulse.config import Profile
from pulse.models import Snapshot

ACTIVE_WINDOW_DAYS = 30


class MarkerError(ValueError):
    """Raised when a README marker pair is missing or malformed."""


def _pattern(name: str) -> re.Pattern[str]:
    return re.compile(
        rf"(<!-- pulse:{re.escape(name)} -->)(.*?)(<!-- /pulse:{re.escape(name)} -->)",
        re.DOTALL,
    )


def replace_sections(readme: str, sections: Mapping[str, str]) -> str:
    """Return a new README with each marked section's body replaced. Idempotent."""
    result = readme
    for name, body in sections.items():
        pattern = _pattern(name)
        if not pattern.search(result):
            raise MarkerError(f"README is missing markers for section '{name}'")
        result = pattern.sub(_replacer(body), result)
    return result


def _replacer(body: str) -> Callable[[re.Match[str]], str]:
    # A function (not a template string) so backslashes in the body are kept literally.
    def replace(match: re.Match[str]) -> str:
        return f"{match.group(1)}\n{body.strip()}\n{match.group(3)}"

    return replace


def manifest(profile: Profile, snapshot: Snapshot) -> str:
    """A Kubernetes-style manifest describing the engineer, partly from live data."""
    shipping = _recently_shipped(snapshot)
    langs = [s.name for s in metrics.language_shares(snapshot) if s.name != "other"][:4]
    lines = [
        "```yaml",
        "apiVersion: human.dev/v1",
        f"kind: {profile.kind}",
        "metadata:",
        f"  name: {profile.handle}",
        "  labels:",
        f"    role: {profile.role}",
        f"    region: {profile.region}",
        "spec:",
        f"  displayName: {profile.display_name}",
        *_work_manifest(profile),
        "  focus:",
        *(f"    - {item}" for item in profile.focus),
        f"  stack: [{', '.join(profile.stack)}]",
        "status:",
        f"  phase: Running  # since {snapshot.created_at:%Y-%m-%d}",
        f"  observedLanguages: [{', '.join(langs)}]  # live, recency-weighted",
    ]
    if shipping:
        lines.append(
            f"  recentlyShipped: [{', '.join(shipping)}]  # public, last {ACTIVE_WINDOW_DAYS}d"
        )
    lines.append("```")
    return "\n".join(lines)


def _work_manifest(profile: Profile) -> list[str]:
    work = profile.work
    if work is None:
        return []
    return [
        f"  employer: {work.company}  # {work.company_url}",
        *(["  building:"] if work.products else []),
        *(f"    - {p.name}: {p.summary}" for p in work.products),
    ]


def work_banner(profile: Profile) -> str:
    """Clickable one-liner about the current role (HTML, every value escaped)."""
    work = profile.work
    if work is None:
        return ""
    company = f'<a href="{escape(work.company_url)}"><b>{escape(work.company)}</b></a>'
    lines = [f"<b>{escape(work.title)}</b> at {company}"]
    lines += [
        f'building <a href="{escape(p.url)}"><b>{escape(p.name)}</b></a> — {escape(p.summary)}'
        for p in work.products
    ]
    return "<br>\n".join(lines)


def _recently_shipped(snapshot: Snapshot) -> list[str]:
    profile_repo = f"{snapshot.login}/{snapshot.login}".lower()
    recent = [
        r
        for r in snapshot.repos
        if not r.is_private
        and not r.is_fork
        and r.name_with_owner.lower() != profile_repo
        and (snapshot.fetched_at - r.pushed_at).days < ACTIVE_WINDOW_DAYS
    ]
    return [r.short_name for r in sorted(recent, key=lambda r: r.pushed_at, reverse=True)[:4]]


def links(profile: Profile) -> str:
    return " · ".join(f"[`{name}`]({url})" for name, url in profile.links)


def footer(snapshot: Snapshot) -> str:
    return (
        f"<sub>last scrape <code>{snapshot.fetched_at:%Y-%m-%d} UTC</code> · "
        "refreshed every 6h by a GitHub Action · rendered by "
        '<a href="pulse"><code>pulse</code></a> — no third-party widgets</sub>'
    )
