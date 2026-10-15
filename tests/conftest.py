"""Deterministic synthetic data shared by the test suite."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from pulse.config import Profile, parse_profile
from pulse.models import Commit, Day, Language, PullRequest, Repo, Snapshot

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)

PROFILE_RAW = {
    "login": "octo",
    "handle": "octo.dev",
    "display_name": "Octo Dev",
    "tagline": "platform engineer · observability",
    "role": "platform-engineer",
    "region": "us-west",
    "timezone": "America/Los_Angeles",
    "focus": ["OpenTelemetry"],
    "stack": ["Go", "Python"],
    "links": {"github": "https://github.com/octo"},
}


def _repo(
    name: str,
    *,
    private: bool = False,
    fork: bool = False,
    pushed_days: int = 1,
    created_days: int = 400,
    langs: tuple[Language, ...] = (),
) -> Repo:
    return Repo(
        name_with_owner=name,
        is_private=private,
        is_fork=fork,
        created_at=NOW - timedelta(days=created_days),
        pushed_at=NOW - timedelta(days=pushed_days),
        stars=3,
        languages=langs,
    )


def make_snapshot() -> Snapshot:
    go = Language("Go", "#00ADD8", 50_000)
    py = Language("Python", "#3572A5", 30_000)
    ts = Language("TypeScript", "#3178c6", 10_000)
    repos = (
        _repo("octo/octo", pushed_days=0),
        _repo("octo/api", pushed_days=2, langs=(go, py)),
        _repo("acme/sdk", pushed_days=40, langs=(ts,)),
        _repo("octo/old", pushed_days=800, created_days=1500, langs=(py,)),
        _repo("octo/forked", fork=True, pushed_days=3, langs=(Language("C", "#555", 999_999),)),
        _repo("private/workload-01", private=True, pushed_days=0, langs=(go,)),
    )
    commits = tuple(
        Commit("octo/api", False, NOW - timedelta(days=d, hours=3), 10, 2) for d in range(0, 6)
    ) + (Commit("private/workload-01", True, NOW - timedelta(days=1, hours=1), 5, 1),)
    pulls = (
        PullRequest(
            "octo/api",
            False,
            NOW - timedelta(days=2, hours=4),
            NOW - timedelta(days=2, hours=2),
            "MERGED",
        ),
        PullRequest(
            "private/workload-01", True, NOW - timedelta(days=3), NOW - timedelta(days=2), "MERGED"
        ),
        PullRequest("acme/sdk", False, NOW - timedelta(days=4), None, "CLOSED"),
        PullRequest("acme/sdk", False, NOW - timedelta(days=1), None, "OPEN"),
    )
    start = NOW.date() - timedelta(days=364)
    calendar = tuple(Day(start + timedelta(days=i), 2 if i % 3 == 0 else 0) for i in range(365))
    return Snapshot(
        login="octo",
        name="Octo Dev",
        created_at=datetime(2018, 10, 18, tzinfo=UTC),
        fetched_at=NOW,
        calendar=calendar,
        repos=repos,
        commits=commits,
        pull_requests=pulls,
        meta={"private_repos": 1},
    )


def empty_snapshot() -> Snapshot:
    return Snapshot(login="octo", name="Octo", created_at=NOW - timedelta(days=10), fetched_at=NOW)


@pytest.fixture
def snapshot() -> Snapshot:
    return make_snapshot()


@pytest.fixture
def profile() -> Profile:
    return parse_profile(PROFILE_RAW)


@pytest.fixture
def today() -> date:
    return NOW.date()
