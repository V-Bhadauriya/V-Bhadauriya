"""Marker-based README section rewriting and generated text blocks."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from html import escape

from pulse import insights, metrics
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
        *_stack_manifest(profile),
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


def _stack_manifest(profile: Profile) -> list[str]:
    groups = profile.stack
    if not groups:
        return []
    if len(groups) == 1 and not groups[0].label:
        return [f"  stack: [{', '.join(groups[0].items)}]"]
    return ["  stack:", *(f"    {g.key}: [{', '.join(g.items)}]" for g in groups)]


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


# --------------------------------------------------------------------------- panel layout


def picture(name: str, alt: str) -> str:
    """Theme-aware image: GitHub swaps in the dark variant for dark-mode readers."""
    return (
        f'<p align="center">\n<picture><source media="(prefers-color-scheme: dark)" '
        f'srcset="assets/{name}-dark.svg"><img src="assets/{name}-light.svg" '
        f'alt="{escape(alt)}" width="100%"></picture>\n</p>'
    )


def hero(profile: Profile, alts: Mapping[str, str]) -> str:
    banner = work_banner(profile)
    parts = [picture("status", alts["status"])]
    if banner:
        parts.append(f'<p align="center">\n{banner}\n</p>')
    parts.append(picture("activity", alts["activity"]))
    return "\n\n".join(parts)


def panels(names_and_alts: list[tuple[str, str]], profile: Profile, snapshot: Snapshot) -> str:
    """Every non-hero panel, one per row, with clickable repo links under 'featured'."""
    blocks = []
    for name, alt in names_and_alts:
        blocks.append(picture(name, alt))
        if name == "featured":
            line = featured_links(profile, snapshot)
            if line:
                blocks.append(f'<p align="center">{line}</p>')
    return "\n\n".join(blocks)


def featured_links(profile: Profile, snapshot: Snapshot) -> str:
    items = insights.featured_repos(snapshot, profile.featured)
    return " · ".join(
        f'<a href="https://github.com/{escape(f.repo.name_with_owner)}">'
        f"<code>{escape(f.repo.short_name)}</code></a>"
        for f in items
    )


def writing(snapshot: Snapshot) -> str:
    if not snapshot.posts:
        return ""
    rows = [
        f'<a href="{escape(p.url)}">{escape(p.title)}</a>'
        + (f" <sub>{p.published:%b %d, %Y}</sub>" if p.published else "")
        for p in snapshot.posts
    ]
    return '<p align="center">\n<b>latest writing</b><br>\n' + "<br>\n".join(rows) + "\n</p>"
