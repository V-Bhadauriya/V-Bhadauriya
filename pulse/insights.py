"""Derived views for the richer panels: service map, logs, churn, reviews, drift, records."""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from itertools import combinations

from pulse import metrics
from pulse.models import Repo, Snapshot
from pulse.privacy import is_anonymised

SERVICE_MAP_DAYS = 90
STALE_PR_DAYS = 3
CRITICAL_PR_DAYS = 14


# --------------------------------------------------------------------------- labels


def service_labels(snapshot: Snapshot) -> dict[str, str]:
    """Display name for every repo: short name if public, language label if private."""
    names = (
        {r.name_with_owner for r in snapshot.repos}
        | {c.repo for c in snapshot.commits}
        | {p.repo for p in snapshot.pull_requests}
        | {r.repo for r in snapshot.reviews}
    )
    labels = metrics.global_private_labels(snapshot)
    return {n: labels.get(n, n.split("/")[-1]) for n in names}


# --------------------------------------------------------------------------- service map


@dataclass(frozen=True)
class Node:
    repo: str
    label: str
    is_private: bool
    events: int


@dataclass(frozen=True)
class Edge:
    a: str
    b: str
    shared_days: int


@dataclass(frozen=True)
class ServiceMap:
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]


def service_map(snapshot: Snapshot, max_nodes: int = 8, max_edges: int = 10) -> ServiceMap:
    """Busiest repos of the last 90 days, linked when you worked on both on the same day."""
    since = snapshot.fetched_at - timedelta(days=SERVICE_MAP_DAYS)
    profile_repo = f"{snapshot.login}/{snapshot.login}".lower()
    days: defaultdict[str, set[date]] = defaultdict(set)
    events: Counter[str] = Counter()
    for repo, at in _activity(snapshot):
        if at >= since and repo.lower() != profile_repo:
            days[repo].add(at.date())
            events[repo] += 1
    top = [repo for repo, _ in events.most_common(max_nodes)]
    labels = service_labels(snapshot)
    nodes = tuple(Node(r, labels.get(r, r), is_anonymised(r), events[r]) for r in top)
    pairs = [Edge(a, b, len(days[a] & days[b])) for a, b in combinations(top, 2)]
    edges = sorted((e for e in pairs if e.shared_days), key=lambda e: -e.shared_days)
    return ServiceMap(nodes, tuple(edges[:max_edges]))


# --------------------------------------------------------------------------- deploy log


@dataclass(frozen=True)
class LogLine:
    at: datetime
    level: str  # MERGE | PR | COMMIT
    service: str
    message: str


def deploy_log(snapshot: Snapshot, limit: int = 10) -> tuple[LogLine, ...]:
    labels = service_labels(snapshot)
    profile_repo = f"{snapshot.login}/{snapshot.login}".lower()
    lines = [
        LogLine(c.committed_at, "COMMIT", labels.get(c.repo, c.repo), c.message or "pushed commit")
        for c in snapshot.commits
        if c.repo.lower() != profile_repo
    ]
    for pr in snapshot.pull_requests:
        service = labels.get(pr.repo, pr.repo)
        title = pr.title or "pull request"
        lines.append(LogLine(pr.created_at, "PR", service, f"opened: {title}"))
        if pr.merged_at:
            lines.append(LogLine(pr.merged_at, "MERGE", service, f"merged: {title}"))
    return tuple(sorted(lines, key=lambda line: line.at, reverse=True)[:limit])


# --------------------------------------------------------------------------- churn


@dataclass(frozen=True)
class ChurnWeek:
    start: date
    additions: int
    deletions: int


def weekly_churn(snapshot: Snapshot, weeks: int = 52) -> tuple[ChurnWeek, ...]:
    end = snapshot.fetched_at.date()
    first = end - timedelta(days=weeks * 7 - 1)
    adds: Counter[int] = Counter()
    dels: Counter[int] = Counter()
    for c in snapshot.commits:
        offset = (c.committed_at.date() - first).days
        if 0 <= offset < weeks * 7:
            adds[offset // 7] += c.additions
            dels[offset // 7] += c.deletions
    return tuple(ChurnWeek(first + timedelta(days=7 * w), adds[w], dels[w]) for w in range(weeks))


# --------------------------------------------------------------------------- reviews


@dataclass(frozen=True)
class ReviewStats:
    count: int
    median_hours: float | None
    p90_hours: float | None
    repos: int
    weekly: tuple[int, ...]


def review_stats(snapshot: Snapshot, weeks: int = 26) -> ReviewStats:
    reviews = snapshot.reviews
    waits = [max((r.reviewed_at - r.pr_created_at).total_seconds() / 3600, 0.0) for r in reviews]
    first = snapshot.fetched_at.date() - timedelta(days=weeks * 7 - 1)
    per_week: Counter[int] = Counter()
    for r in reviews:
        offset = (r.reviewed_at.date() - first).days
        if 0 <= offset < weeks * 7:
            per_week[offset // 7] += 1
    return ReviewStats(
        count=len(reviews),
        median_hours=statistics.median(waits) if waits else None,
        p90_hours=metrics.percentile(waits, 0.9) if waits else None,
        repos=len({r.repo for r in reviews}),
        weekly=tuple(per_week[w] for w in range(weeks)),
    )


# --------------------------------------------------------------------------- language drift


@dataclass(frozen=True)
class Drift:
    months: tuple[date, ...]
    series: tuple[tuple[str, str, tuple[float, ...]], ...]  # (language, color, shares)


def language_drift(snapshot: Snapshot, months: int = 12, top: int = 5) -> Drift:
    """Share of commits per month by each repo's main language."""
    primary = {r.name_with_owner: r.languages[0] for r in snapshot.repos if r.languages}
    starts = _month_starts(snapshot.fetched_at.date(), months)
    index = {(m.year, m.month): i for i, m in enumerate(starts)}
    counts: defaultdict[str, list[int]] = defaultdict(lambda: [0] * months)
    colors: dict[str, str] = {}
    for c in snapshot.commits:
        lang = primary.get(c.repo)
        slot = index.get((c.committed_at.year, c.committed_at.month))
        if lang and slot is not None:
            counts[lang.name][slot] += 1
            colors[lang.name] = lang.color
    leaders = sorted(counts, key=lambda n: -sum(counts[n]))[:top]
    rest = [sum(counts[n][i] for n in counts if n not in leaders) for i in range(months)]
    totals = [sum(counts[n][i] for n in counts) for i in range(months)]
    named = [(n, colors[n], counts[n]) for n in leaders]
    if any(rest):
        named.append(("other", "#8b949e", rest))
    first = _first_meaningful(totals)
    if first is None:
        return Drift(tuple(starts), ())
    series = tuple(
        (name, color, _carry_shares(values, totals)[first:]) for name, color, values in named
    )
    return Drift(tuple(starts[first:]), series)


def _first_meaningful(totals: list[int], share: float = 0.05) -> int | None:
    """Skip a thin lead-in (e.g. two stray commits a year ago) that would distort shares."""
    peak = max(totals, default=0)
    return next((i for i, t in enumerate(totals) if peak and t >= peak * share), None)


def _carry_shares(values: list[int], totals: list[int]) -> tuple[float, ...]:
    """Monthly share; months with no commits repeat the previous month instead of dropping
    to zero, so a quiet month doesn't look like a language disappearing."""
    shares: list[float] = []
    for value, total in zip(values, totals, strict=True):
        shares.append(value / total if total else (shares[-1] if shares else 0.0))
    return tuple(shares)


def _month_starts(today: date, months: int) -> list[date]:
    year, month = today.year, today.month
    starts = []
    for _ in range(months):
        starts.append(date(year, month, 1))
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    return starts[::-1]


# --------------------------------------------------------------------------- records


@dataclass(frozen=True)
class Records:
    longest_streak: int
    busiest_day: tuple[date, int] | None
    busiest_month: tuple[date, int] | None
    biggest_commit: tuple[int, str] | None  # (lines changed, service)
    fastest_merge_minutes: float | None
    top_service: tuple[str, int] | None
    monthly: tuple[tuple[date, int], ...]


def year_records(snapshot: Snapshot) -> Records:
    days = metrics.daily_activity(snapshot)
    starts = _month_starts(snapshot.fetched_at.date(), 12)
    per_month = Counter((d.year, d.month) for d, c in days for _ in range(c))
    monthly = tuple((m, per_month[(m.year, m.month)]) for m in starts)
    labels = service_labels(snapshot)
    biggest = max(snapshot.commits, key=lambda c: c.additions + c.deletions, default=None)
    merges = [
        (p.merged_at - p.created_at).total_seconds() / 60
        for p in snapshot.pull_requests
        if p.merged_at
    ]
    activity = Counter(repo for repo, _ in _activity(snapshot))
    top = activity.most_common(1)
    _, longest = metrics.streaks(snapshot)
    totals = metrics.activity_totals(snapshot)
    return Records(
        longest_streak=longest,
        busiest_day=totals.busiest_day,
        busiest_month=max(monthly, key=lambda m: m[1]) if any(c for _, c in monthly) else None,
        biggest_commit=(
            (biggest.additions + biggest.deletions, labels.get(biggest.repo, biggest.repo))
            if biggest
            else None
        ),
        fastest_merge_minutes=min(merges) if merges else None,
        top_service=(labels.get(top[0][0], top[0][0]), top[0][1]) if top else None,
        monthly=monthly,
    )


# --------------------------------------------------------------------------- alerts


@dataclass(frozen=True)
class Alert:
    severity: str  # warning | critical
    service: str
    title: str
    age_days: int


def stale_prs(snapshot: Snapshot) -> tuple[Alert, ...]:
    labels = service_labels(snapshot)
    alerts = []
    for pr in snapshot.pull_requests:
        age = (snapshot.fetched_at - pr.created_at).days
        if pr.state == "OPEN" and age >= STALE_PR_DAYS:
            severity = "critical" if age >= CRITICAL_PR_DAYS else "warning"
            title = pr.title or "pull request awaiting merge"
            alerts.append(Alert(severity, labels.get(pr.repo, pr.repo), title, age))
    return tuple(sorted(alerts, key=lambda a: -a.age_days))


# --------------------------------------------------------------------------- featured


@dataclass(frozen=True)
class Featured:
    repo: Repo
    commits: int


def featured_repos(
    snapshot: Snapshot, pinned: tuple[str, ...] = (), limit: int = 4
) -> tuple[Featured, ...]:
    """Pinned public repos from profile.yml, else your most active public repos."""
    commits = Counter(c.repo for c in snapshot.commits)
    public = {
        r.name_with_owner.lower(): r
        for r in snapshot.repos
        if not r.is_private
        and not r.is_fork
        and r.name_with_owner.lower() != f"{snapshot.login}/{snapshot.login}".lower()
    }
    if pinned:
        chosen = [public[n.lower()] for n in pinned if n.lower() in public]
    else:
        chosen = sorted(
            public.values(), key=lambda r: (-commits[r.name_with_owner], -r.pushed_at.timestamp())
        )
    return tuple(Featured(r, commits[r.name_with_owner]) for r in chosen[:limit])


# --------------------------------------------------------------------------- helpers


def _activity(snapshot: Snapshot) -> list[tuple[str, datetime]]:
    return [(c.repo, c.committed_at) for c in snapshot.commits] + [
        (p.repo, p.created_at) for p in snapshot.pull_requests
    ]
