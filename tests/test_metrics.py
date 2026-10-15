from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from conftest import NOW, empty_snapshot

from pulse import metrics
from pulse.models import Commit


def test_daily_activity_takes_max_of_calendar_and_own_events(snapshot):
    days = dict(metrics.daily_activity(snapshot))
    assert len(days) == 365
    # Today: calendar says 0 or 2; own events = 1 commit (api, -3h) + nothing else.
    today = NOW.date()
    assert days[today] >= 1


def test_streaks_and_totals(snapshot):
    current, longest = metrics.streaks(snapshot)
    assert longest >= current >= 1
    assert metrics.total_activity(snapshot) > 0


def test_streak_survives_quiet_today():
    snap = empty_snapshot()
    assert metrics.streaks(snap) == (0, 0)


def test_uptime_label():
    up = metrics.uptime(datetime(2018, 10, 18, tzinfo=UTC), NOW)
    assert up.years == 7
    assert up.label().startswith("7y ")


def test_availability_and_throughput(snapshot):
    assert 0 < metrics.availability(snapshot) <= 1
    assert metrics.throughput(snapshot) > 0
    assert metrics.availability(empty_snapshot()) == 0


def test_mttr_and_merge_rate(snapshot):
    # merged PRs: 2h and 24h -> median 13h
    assert metrics.mttr_hours(snapshot) == 13.0
    assert metrics.merge_rate(snapshot) == 2 / 3
    assert metrics.mttr_hours(empty_snapshot()) is None
    assert metrics.merge_rate(empty_snapshot()) is None


def test_percentile():
    assert metrics.percentile([], 0.5) == 0
    assert metrics.percentile([1, 2, 3, 4], 0.5) == 2.5
    assert metrics.percentile([5], 0.95) == 5


def test_weekly_series_has_52_weeks(snapshot):
    weeks = metrics.weekly_series(snapshot)
    assert len(weeks) == 52
    assert all(w.count >= 0 for w in weeks)


def test_heatmap_uses_local_timezone(snapshot):
    matrix = metrics.heatmap(snapshot, ZoneInfo("America/Los_Angeles"))
    assert len(matrix) == 7 and all(len(row) == 24 for row in matrix)
    # 7 commits + 4 PRs opened; merges excluded
    assert sum(map(sum, matrix)) == 11
    utc = metrics.heatmap(snapshot, ZoneInfo("UTC"))
    assert utc != matrix


def test_trace_spans_window_and_privacy(snapshot):
    spans = metrics.trace_spans(snapshot)
    names = {s.service: s for s in spans}
    assert names["private · Go service"].is_private
    assert not any("workload" in s.service for s in spans)
    assert "octo" not in names  # profile repo excluded
    assert not names["api"].is_private
    assert all(s.start <= s.end for s in spans)
    assert list(spans) == sorted(spans, key=lambda s: s.start)


def test_trace_spans_respects_limit(snapshot):
    assert len(metrics.trace_spans(snapshot, max_spans=1)) == 1


def test_language_shares_skip_forks_and_sum_to_one(snapshot):
    shares = metrics.language_shares(snapshot)
    names = [s.name for s in shares]
    assert "C" not in names  # only present in a fork
    assert names[0] == "Go"
    assert abs(sum(s.share for s in shares) - 1) < 1e-9
    assert metrics.language_shares(empty_snapshot()) == ()


def test_pods_exclude_private_fork_and_profile_repo(snapshot):
    pods = metrics.pods(snapshot)
    names = [p.name for p in pods]
    assert names == ["api", "sdk", "old"]
    status = {p.name: p.status for p in pods}
    assert status == {"api": "Running", "sdk": "Idle", "old": "Completed"}
    api = next(p for p in pods if p.name == "api")
    assert api.restarts == 7  # 6 commits + 1 PR
    assert api.language == "Go"


def test_last_deploy_hides_private_names(snapshot):
    name, when = metrics.last_deploy(snapshot)
    assert name == "private repo"
    assert when <= NOW
    assert metrics.last_deploy(empty_snapshot()) is None


def test_coarse_age():
    assert metrics.coarse_age(timedelta(hours=20)) == "today"
    assert metrics.coarse_age(timedelta(days=3, hours=2)) == "3d ago"


def test_empty_today_is_not_downtime():
    snap = empty_snapshot()
    yesterday = Commit("octo/api", False, NOW - timedelta(days=1), 1, 0)
    active = replace(snap, commits=(yesterday,))
    assert metrics.availability(active, days=1) == 1.0


def test_humanize_age():
    assert metrics.humanize_age(timedelta(days=3, hours=4)) == "3d"
    assert metrics.humanize_age(timedelta(hours=5)) == "5h"
    assert metrics.humanize_age(timedelta(minutes=7)) == "7m"
    assert metrics.humanize_age(timedelta(seconds=-5)) == "0s"


def test_activity_totals(snapshot):
    totals = metrics.activity_totals(snapshot)
    assert totals.commits == 7
    assert totals.prs_opened == 4
    assert totals.prs_merged == 2
    assert (totals.additions, totals.deletions) == (65, 13)
    assert totals.repos == 3  # api, sdk, private workload
    assert 0 < totals.active_days <= 365
    assert totals.busiest_day is not None
    assert metrics.activity_totals(empty_snapshot()).busiest_day is None


def test_calendar_weeks_are_monday_first_and_padded(snapshot):
    weeks = metrics.calendar_weeks(snapshot)
    assert all(len(w) == 7 for w in weeks)
    days = [d for w in weeks for d in w if d]
    assert len(days) == 365
    assert all(d[0].weekday() == row for w in weeks for row, d in enumerate(w) if d)


def test_compact_number():
    assert metrics.compact_number(999) == "999"
    assert metrics.compact_number(1_500) == "1.5k"
    assert metrics.compact_number(2_000_000) == "2M"


def test_private_labels_number_only_on_collision(snapshot):
    from dataclasses import replace as dc_replace

    from pulse.models import Language, Repo

    go = Language("Go", "#00ADD8", 1)
    extra = Repo("private/workload-02", True, False, NOW, NOW, languages=(go,))
    bare = Repo("private/workload-03", True, False, NOW, NOW)
    snap = dc_replace(snapshot, repos=(*snapshot.repos, extra, bare))
    labels = metrics.private_labels(
        snap, ["private/workload-01", "private/workload-02", "private/workload-03"]
    )
    assert labels == {
        "private/workload-01": "private · Go service 1",
        "private/workload-02": "private · Go service 2",
        "private/workload-03": "private · app service",
    }
