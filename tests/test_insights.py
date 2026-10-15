from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from conftest import NOW, empty_snapshot

from pulse import insights
from pulse.models import PullRequest, Review


def test_service_labels_hide_private_names(snapshot):
    labels = insights.service_labels(snapshot)
    assert labels["octo/api"] == "api"
    assert labels["private/workload-01"] == "private · Go service"


def test_service_map_nodes_and_edges(snapshot):
    smap = insights.service_map(snapshot)
    repos = [n.repo for n in smap.nodes]
    assert "octo/octo" not in repos
    assert repos[0] == "octo/api"  # busiest
    assert all(e.shared_days > 0 for e in smap.edges)
    assert insights.service_map(empty_snapshot()).nodes == ()


def test_deploy_log_is_newest_first_and_skips_profile_repo(snapshot):
    lines = insights.deploy_log(snapshot, limit=50)
    assert [line.at for line in lines] == sorted((line.at for line in lines), reverse=True)
    assert {line.level for line in lines} == {"COMMIT", "PR", "MERGE"}
    assert all(line.service != "octo" for line in lines)
    assert len(insights.deploy_log(snapshot, limit=3)) == 3


def test_weekly_churn(snapshot):
    weeks = insights.weekly_churn(snapshot, weeks=4)
    assert len(weeks) == 4
    assert sum(w.additions for w in weeks) == 65
    assert sum(w.deletions for w in weeks) == 13


def test_review_stats():
    snap = replace(
        empty_snapshot(),
        reviews=(
            Review("octo/a", False, NOW - timedelta(days=2), NOW - timedelta(days=2, hours=-2)),
            Review("octo/b", False, NOW - timedelta(days=1), NOW - timedelta(hours=20)),
        ),
    )
    stats = insights.review_stats(snap)
    assert stats.count == 2 and stats.repos == 2
    assert stats.median_hours == 3.0
    assert sum(stats.weekly) == 2
    empty = insights.review_stats(empty_snapshot())
    assert empty.median_hours is None and empty.p90_hours is None


def test_language_drift_shares_sum_to_one(snapshot):
    drift = insights.language_drift(snapshot)
    assert drift.series
    for i in range(len(drift.months)):
        assert abs(sum(s[2][i] for s in drift.series) - 1) < 1e-9
    assert insights.language_drift(empty_snapshot()).series == ()


def test_carry_shares_and_first_meaningful():
    assert insights._carry_shares([1, 0, 2], [2, 0, 2]) == (0.5, 0.5, 1.0)
    assert insights._first_meaningful([1, 0, 100, 50]) == 2
    assert insights._first_meaningful([0, 0]) is None


def test_year_records(snapshot):
    rec = insights.year_records(snapshot)
    assert rec.longest_streak >= 1
    assert rec.biggest_commit == (12, "api")
    assert rec.fastest_merge_minutes == 120
    assert rec.top_service and rec.top_service[0] == "api"
    assert len(rec.monthly) == 12
    empty = insights.year_records(empty_snapshot())
    assert empty.biggest_commit is None and empty.fastest_merge_minutes is None


def test_stale_prs_severity():
    prs = (
        PullRequest("octo/a", False, NOW - timedelta(days=20), None, "OPEN", "big refactor"),
        PullRequest("octo/b", False, NOW - timedelta(days=5), None, "OPEN"),
        PullRequest("octo/c", False, NOW - timedelta(days=1), None, "OPEN"),
        PullRequest("octo/d", False, NOW - timedelta(days=30), NOW, "MERGED"),
    )
    alerts = insights.stale_prs(replace(empty_snapshot(), pull_requests=prs))
    assert [(a.severity, a.age_days) for a in alerts] == [("critical", 20), ("warning", 5)]
    assert alerts[1].title == "pull request awaiting merge"


def test_featured_auto_and_pinned(snapshot):
    auto = insights.featured_repos(snapshot)
    names = [f.repo.short_name for f in auto]
    assert names[0] == "api" and "forked" not in names and "octo" not in names
    pinned = insights.featured_repos(snapshot, ("acme/sdk", "nope/missing"))
    assert [f.repo.short_name for f in pinned] == ["sdk"]
