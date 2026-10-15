"""Pure metric functions: Snapshot in, plain immutable values out."""

from __future__ import annotations

import math
import statistics
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo

from pulse import config
from pulse.models import Repo, Snapshot
from pulse.privacy import is_anonymised

RUNNING_DAYS = 30
IDLE_DAYS = 365
LANGUAGE_HALF_LIFE_DAYS = 180.0
MAX_LANGUAGES = 6


@dataclass(frozen=True)
class Uptime:
    years: int
    days: int

    def label(self) -> str:
        return f"{self.years}y {self.days}d"


@dataclass(frozen=True)
class Week:
    start: date
    count: int


@dataclass(frozen=True)
class Event:
    kind: str  # "commit" | "pr" | "merge"
    at: datetime


@dataclass(frozen=True)
class Span:
    service: str
    is_private: bool
    start: datetime
    end: datetime
    events: tuple[Event, ...]


@dataclass(frozen=True)
class LanguageShare:
    name: str
    color: str
    share: float  # 0..1


@dataclass(frozen=True)
class Pod:
    name: str
    status: str  # Running | Idle | Completed
    restarts: int
    age_days: int
    language: str


# --------------------------------------------------------------------------- activity


def daily_activity(snapshot: Snapshot) -> tuple[tuple[date, int], ...]:
    """Per-day activity for the lookback window.

    The public calendar can omit private work, so each day takes the larger of the
    calendar count and the events we fetched directly (commits + PRs opened).
    """
    end = snapshot.fetched_at.date()
    start = end - timedelta(days=config.LOOKBACK_DAYS - 1)
    calendar = {d.day: d.count for d in snapshot.calendar}
    own = Counter(e.at.date() for e in _events(snapshot) if e.kind != "merge")
    span = (start + timedelta(days=i) for i in range((end - start).days + 1))
    return tuple((day, max(calendar.get(day, 0), own.get(day, 0))) for day in span)


def weekly_series(snapshot: Snapshot, weeks: int = 52) -> tuple[Week, ...]:
    days = daily_activity(snapshot)[-weeks * 7 :]
    return tuple(
        Week(days[i][0], sum(c for _, c in days[i : i + 7])) for i in range(0, len(days), 7)
    )


def total_activity(snapshot: Snapshot) -> int:
    return sum(c for _, c in daily_activity(snapshot))


def streaks(snapshot: Snapshot) -> tuple[int, int]:
    """(current, longest) run of consecutive active days."""
    longest = run = 0
    for _, count in daily_activity(snapshot):
        run = run + 1 if count else 0
        longest = max(longest, run)
    current = 0
    # Today may not have activity yet; let the streak survive until tomorrow.
    for _, count in reversed(settled_activity(snapshot)):
        if not count:
            break
        current += 1
    return current, longest


def uptime(created_at: datetime, now: datetime) -> Uptime:
    total = (now - created_at).days
    return Uptime(years=total // 365, days=total % 365)


def settled_activity(snapshot: Snapshot) -> tuple[tuple[date, int], ...]:
    """Daily activity without today when today has nothing yet (the day is still running)."""
    days = daily_activity(snapshot)
    return days[:-1] if days and days[-1][1] == 0 else days


def availability(snapshot: Snapshot, days: int = 30) -> float:
    """Share of days with any activity in a rolling SRE-style window."""
    window = settled_activity(snapshot)[-days:]
    return sum(1 for _, c in window if c) / len(window) if window else 0.0


def throughput(snapshot: Snapshot, weeks: int = 12) -> float:
    window = settled_activity(snapshot)[-weeks * 7 :]
    return sum(c for _, c in window) * 7 / len(window) if window else 0.0


def mttr_hours(snapshot: Snapshot) -> float | None:
    """Median hours from PR open to merge, across merged PRs in the window."""
    durations = [
        (p.merged_at - p.created_at).total_seconds() / 3600
        for p in snapshot.pull_requests
        if p.merged_at is not None
    ]
    return statistics.median(durations) if durations else None


def merge_rate(snapshot: Snapshot) -> float | None:
    closed = [p for p in snapshot.pull_requests if p.state in ("MERGED", "CLOSED")]
    if not closed:
        return None
    return sum(1 for p in closed if p.state == "MERGED") / len(closed)


def percentile(values: Sequence[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * pct
    low, high = math.floor(rank), math.ceil(rank)
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


# --------------------------------------------------------------------------- heatmap


def heatmap(snapshot: Snapshot, tz: tzinfo) -> tuple[tuple[int, ...], ...]:
    """7 x 24 matrix (Mon..Sun x hour) of commits and PRs opened, in local time."""
    counts: Counter[tuple[int, int]] = Counter()
    for event in _events(snapshot):
        if event.kind == "merge":
            continue
        local = event.at.astimezone(tz)
        counts[(local.weekday(), local.hour)] += 1
    return tuple(tuple(counts[(d, h)] for h in range(24)) for d in range(7))


# --------------------------------------------------------------------------- trace


def trace_spans(snapshot: Snapshot, max_spans: int = 7) -> tuple[Span, ...]:
    """Activity in the trace window grouped into one span per service (repo).

    Private repos are labelled by their main language only, e.g. "private · Go service".
    The profile repo itself is left out: its commits are just the refresh bot.
    """
    window_start = snapshot.fetched_at - timedelta(days=config.TRACE_WINDOW_DAYS)
    profile_repo = f"{snapshot.login}/{snapshot.login}".lower()
    grouped: dict[str, list[Event]] = {}
    for repo, event in _events_with_repo(snapshot):
        if event.at >= window_start and repo.lower() != profile_repo:
            grouped[repo] = [*grouped.get(repo, []), event]
    busiest = sorted(grouped, key=lambda r: (-len(grouped[r]), r))[:max_spans]
    labels = global_private_labels(snapshot)
    spans = [
        Span(
            service=labels.get(repo, repo.split("/")[-1]),
            is_private=is_anonymised(repo),
            start=min(e.at for e in grouped[repo]),
            end=max(e.at for e in grouped[repo]),
            events=tuple(sorted(grouped[repo], key=_at)),
        )
        for repo in busiest
    ]
    return tuple(sorted(spans, key=lambda s: s.start))


def global_private_labels(snapshot: Snapshot) -> dict[str, str]:
    """Private labels numbered across *all* private repos by activity, so a label like
    "private · Go service 2" means the same repo in every panel."""
    activity = Counter(c.repo for c in snapshot.commits) + Counter(
        p.repo for p in snapshot.pull_requests
    )
    names = (
        {r.name_with_owner for r in snapshot.repos}
        | set(activity)
        | {r.repo for r in snapshot.reviews}
    )
    ordered = sorted((n for n in names if is_anonymised(n)), key=lambda n: (-activity[n], n))
    return private_labels(snapshot, ordered)


def private_labels(snapshot: Snapshot, aliases: list[str]) -> dict[str, str]:
    """Human-readable names for private repos that reveal nothing but the main language.

    Numbered only when two private repos share a language: "private · Go service 2".
    """
    language = {
        r.name_with_owner: (r.languages[0].name if r.languages else "") for r in snapshot.repos
    }
    bases = {a: f"private · {language.get(a) or 'app'} service" for a in aliases}
    totals = Counter(bases.values())
    seen: Counter[str] = Counter()
    labels = {}
    for alias_name in aliases:
        base = bases[alias_name]
        seen[base] += 1
        labels[alias_name] = base if totals[base] == 1 else f"{base} {seen[base]}"
    return labels


def _at(event: Event) -> datetime:
    return event.at


# --------------------------------------------------------------------------- languages


def language_shares(snapshot: Snapshot) -> tuple[LanguageShare, ...]:
    """Language mix weighted by bytes and by how recently each repo was pushed."""
    weights: Counter[str] = Counter()
    colors: dict[str, str] = {}
    for repo in snapshot.repos:
        if repo.is_fork:
            continue
        age = max((snapshot.fetched_at - repo.pushed_at).days, 0)
        decay = 0.5 ** (age / LANGUAGE_HALF_LIFE_DAYS)
        for lang in repo.languages:
            weights[lang.name] += lang.size * decay
            colors.setdefault(lang.name, lang.color)
    total = sum(weights.values())
    if not total:
        return ()
    top = weights.most_common(MAX_LANGUAGES)
    shares = [LanguageShare(n, colors[n], w / total) for n, w in top]
    rest = 1.0 - sum(s.share for s in shares)
    if rest > 0.005:
        shares.append(LanguageShare("other", "#8b949e", rest))
    return tuple(shares)


# --------------------------------------------------------------------------- pods


def pods(snapshot: Snapshot, limit: int = 8) -> tuple[Pod, ...]:
    """Public, non-fork repositories presented as Kubernetes pods."""
    restarts = Counter(c.repo for c in snapshot.commits)
    for pr in snapshot.pull_requests:
        restarts[pr.repo] += 1
    profile_repo = f"{snapshot.login}/{snapshot.login}".lower()
    public = [
        r
        for r in snapshot.repos
        if not r.is_private and not r.is_fork and r.name_with_owner.lower() != profile_repo
    ]
    public.sort(key=lambda r: r.pushed_at, reverse=True)
    return tuple(_pod(r, restarts[r.name_with_owner], snapshot.fetched_at) for r in public[:limit])


def _pod(repo: Repo, restarts: int, now: datetime) -> Pod:
    idle = (now - repo.pushed_at).days
    status = "Running" if idle < RUNNING_DAYS else "Idle" if idle < IDLE_DAYS else "Completed"
    language = repo.languages[0].name if repo.languages else "-"
    return Pod(repo.short_name, status, restarts, (now - repo.created_at).days, language)


def last_deploy(snapshot: Snapshot) -> tuple[str, datetime] | None:
    """Most recently pushed public repo (private pushes are reported generically)."""
    profile_repo = f"{snapshot.login}/{snapshot.login}".lower()
    candidates = [r for r in snapshot.repos if r.name_with_owner.lower() != profile_repo]
    if not candidates:
        return None
    latest = max(candidates, key=lambda r: r.pushed_at)
    name = config.PRIVATE_LABEL if latest.is_private else latest.short_name
    return name, latest.pushed_at


# --------------------------------------------------------------------------- helpers


def _events(snapshot: Snapshot) -> list[Event]:
    return [event for _, event in _events_with_repo(snapshot)]


def _events_with_repo(snapshot: Snapshot) -> list[tuple[str, Event]]:
    commits = [(c.repo, Event("commit", c.committed_at)) for c in snapshot.commits]
    opened = [(p.repo, Event("pr", p.created_at)) for p in snapshot.pull_requests]
    merged = [(p.repo, Event("merge", p.merged_at)) for p in snapshot.pull_requests if p.merged_at]
    return [*commits, *opened, *merged]


def coarse_age(delta: timedelta) -> str:
    """Day-granular age, so the label doesn't change on every 6-hourly run."""
    days = max(delta.days, 0)
    return "today" if days == 0 else f"{days}d ago"


def humanize_age(delta: timedelta) -> str:
    seconds = max(int(delta.total_seconds()), 0)
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{seconds // size}{unit}"
    return f"{seconds}s"


# --------------------------------------------------------------------------- yearly totals


@dataclass(frozen=True)
class Totals:
    commits: int
    prs_opened: int
    prs_merged: int
    additions: int
    deletions: int
    repos: int
    active_days: int
    busiest_day: tuple[date, int] | None


def activity_totals(snapshot: Snapshot) -> Totals:
    """Headline counts for the lookback window (commits, PRs, line churn, reach)."""
    days = daily_activity(snapshot)
    busiest = max(days, key=lambda d: d[1]) if days else None
    touched = {c.repo for c in snapshot.commits} | {p.repo for p in snapshot.pull_requests}
    return Totals(
        commits=len(snapshot.commits),
        prs_opened=len(snapshot.pull_requests),
        prs_merged=sum(1 for p in snapshot.pull_requests if p.merged_at is not None),
        additions=sum(c.additions for c in snapshot.commits),
        deletions=sum(c.deletions for c in snapshot.commits),
        repos=len(touched),
        active_days=sum(1 for _, c in days if c),
        busiest_day=busiest if busiest and busiest[1] else None,
    )


def calendar_weeks(snapshot: Snapshot) -> tuple[tuple[tuple[date, int] | None, ...], ...]:
    """Daily activity laid out as Monday-first week columns (None pads the edges)."""
    days = daily_activity(snapshot)
    if not days:
        return ()
    lead = days[0][0].weekday()
    padded: list[tuple[date, int] | None] = [*([None] * lead), *days]
    padded = [*padded, *([None] * (-len(padded) % 7))]
    return tuple(tuple(padded[i : i + 7]) for i in range(0, len(padded), 7))


def compact_number(value: int) -> str:
    for suffix, size in (("M", 1_000_000), ("k", 1_000)):
        if abs(value) >= size:
            return f"{value / size:.1f}".rstrip("0").rstrip(".") + suffix
    return f"{value:,}"


TOKEN_WARN_DAYS = 14


def token_days_left(snapshot: Snapshot) -> int | None:
    """Days until the PAT expires, from the header GitHub returns; None if unknown."""
    raw = snapshot.meta.get("token_expires")
    if not raw:
        return None
    try:
        return (date.fromisoformat(str(raw)) - snapshot.fetched_at.date()).days
    except ValueError:
        return None
