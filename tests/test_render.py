from __future__ import annotations

from xml.etree import ElementTree

import pytest
from conftest import PROFILE_RAW, empty_snapshot

from pulse.config import MAX_SVG_BYTES, parse_profile
from pulse.render import PANELS, activity, heatmap, pods, resources, slo, status, timeseries
from pulse.render.context import RenderContext
from pulse.render.svg import Markup, el, truncate
from pulse.render.theme import DARK, LIGHT, THEMES, status_color

SVG_NS = "{http://www.w3.org/2000/svg}"


@pytest.mark.parametrize("theme", THEMES, ids=lambda t: t.name)
@pytest.mark.parametrize("name", list(PANELS))
def test_every_panel_is_valid_small_and_accessible(name, theme, snapshot, profile):
    svg = str(PANELS[name](RenderContext(snapshot, profile, theme)))
    root = ElementTree.fromstring(svg)
    assert root.tag == f"{SVG_NS}svg"
    assert root.attrib["role"] == "img"
    assert root.find(f"{SVG_NS}title") is not None
    assert "prefers-reduced-motion" in svg
    assert theme.accent in svg
    assert len(svg.encode()) < MAX_SVG_BYTES


@pytest.mark.parametrize("name", list(PANELS))
def test_panels_render_with_no_data(name, profile):
    svg = str(PANELS[name](RenderContext(empty_snapshot(), profile, DARK)))
    ElementTree.fromstring(svg)


def test_untrusted_text_is_escaped(snapshot):
    evil = parse_profile({**PROFILE_RAW, "tagline": "<script>alert(1)</script>&"})
    svg = str(status.render(RenderContext(snapshot, evil, LIGHT)))
    assert "<script>" not in svg
    ElementTree.fromstring(svg)


def test_el_builder_escapes_and_skips_none():
    out = el("text", {"class_": "a", "data_x": None, "text_anchor": "end"}, "<b>", None)
    assert out == '<text class="a" text-anchor="end">&lt;b&gt;</text>'
    assert el("g", None, Markup("<x/>")) == "<g><x/></g>"
    assert el("rect", {"x": 1.5000}) == '<rect x="1.5"/>'


def test_truncate():
    assert truncate("abc", 5) == "abc"
    assert truncate("abcdef", 4) == "abc…"


def test_status_color_thresholds():
    assert status_color(DARK, 0.9) == DARK.ok
    assert status_color(DARK, 0.5) == DARK.warn
    assert status_color(DARK, 0.1) == DARK.crit
    assert status_color(DARK, 0.1, invert=True) == DARK.ok


def test_ecg_path_spikes_only_on_active_days():
    flat = status.ecg_path([], 0, 100, 10, 50)
    assert flat.count("L") == 1
    spiky = status.ecg_path([0, 3, 0], 0, 90, 10, 50)
    assert spiky.count("L") == 5 + 1  # five points for the one spike, plus the closing segment
    assert spiky.startswith("M0.0,50.0")


def test_slo_helpers(snapshot, profile):
    assert slo.format_hours(0.5) == "30m"
    assert slo.format_hours(5) == "5.0h"
    assert slo.format_hours(72) == "3d"
    assert slo.arc_path(0, 0, 10).startswith("M")
    gauges = slo.gauges(RenderContext(snapshot, profile, DARK))
    assert [g.label for g in gauges] == ["AVAILABILITY", "THROUGHPUT", "MTTR", "MERGE RATE"]
    assert all(0 <= g.ratio <= 1 for g in gauges)


def test_timeseries_smooth_path():
    assert timeseries.smooth_path([]) == ""
    assert timeseries.smooth_path([(1, 2)]) == "M1.0,2.0"
    assert timeseries.smooth_path([(0, 0), (10, 10), (20, 0)]).count("C") == 2


def test_heatmap_intensity():
    assert heatmap.intensity(0, 10) == 0
    assert heatmap.intensity(10, 10) == pytest.approx(1.0)
    assert 0.18 < heatmap.intensity(1, 10) < 1


def test_resource_segments():
    assert resources.lit_segments(0, 1) == 0
    assert resources.lit_segments(0.5, 0.5) == resources.SEGMENTS
    assert resources.lit_segments(0.001, 0.5) == 1


def test_pod_age_format():
    assert pods.format_age(12) == "12d"
    assert pods.format_age(365) == "1y"
    assert pods.format_age(800) == "2y2m"


def test_no_private_alias_owner_leaks_into_assets(snapshot, profile):
    for theme in THEMES:
        for renderer in PANELS.values():
            svg = str(renderer(RenderContext(snapshot, profile, theme)))
            assert "workload" not in svg


def test_activity_counters(snapshot):
    from pulse import metrics

    cells = activity.counter_cells(metrics.activity_totals(snapshot))
    labels = [c[0] for c in cells]
    assert labels == ["COMMITS", "PRS OPENED", "PRS MERGED", "LINES", "REPOS", "ACTIVE DAYS"]
    assert dict((c[0], c[1]) for c in cells)["LINES"] == "+65 −13"


def test_timeseries_scale_ceiling():
    assert timeseries._nice_ceiling(511) == 600
    assert timeseries._nice_ceiling(2500) == 3000


def test_toolchain_layout_wraps_and_sizes():
    from pulse.config import StackGroup
    from pulse.render import toolchain

    items = tuple(f"tool-{i:02d}" for i in range(20))
    lines = toolchain.layout(items)
    assert len(lines) > 1
    assert all(x + w <= toolchain.CHIPS_RIGHT for line in lines for _, x, w in line)
    assert [label for line in lines for label, _, _ in line] == list(items)
    groups = (StackGroup("A", items), StackGroup("B", ("x",)))
    assert toolchain.height_for(groups) == toolchain.TOP + (len(lines) + 1) * toolchain.LINE_H + 10


def _rich_profile():
    from conftest import PROFILE_RAW

    return parse_profile(
        {
            **PROFILE_RAW,
            "certifications": [
                {"name": "CKA", "issuer": "CNCF", "issued": 2023, "expires": 2026},
                {"name": "Old cert", "issuer": "X", "issued": 2015, "expires": 2018},
            ],
            "experience": [
                {"title": "Engineer", "org": "Old Co", "start": "2019-01", "end": "2022-06"},
                {"title": "Data Scientist", "org": "Acme", "start": "2022-07", "summary": "LLMs"},
            ],
        }
    )


def test_optional_panels_render_configured_content(snapshot):
    from pulse.render import certs, enabled_specs, experience

    profile = _rich_profile()
    names = [s.name for s in enabled_specs(profile)]
    assert names[-2:] == ["experience", "certs"]
    cert_svg = str(certs.render(RenderContext(snapshot, profile, DARK)))
    assert "CKA" in cert_svg and ">False<" in cert_svg and ">True<" in cert_svg
    exp_svg = str(experience.render(RenderContext(snapshot, profile, LIGHT)))
    assert "deployed" in exp_svg and "superseded" in exp_svg and "Acme" in exp_svg


def test_optional_panels_hidden_by_default(profile):
    from pulse.render import enabled_specs

    names = [s.name for s in enabled_specs(profile)]
    assert "certs" not in names and "experience" not in names


def test_alerts_and_reviews_with_data(snapshot, profile):
    from dataclasses import replace
    from datetime import timedelta

    from conftest import NOW

    from pulse.models import PullRequest, Review
    from pulse.render import alerts, reviews

    stale = tuple(
        PullRequest("octo/api", False, NOW - timedelta(days=4 + i), None, "OPEN", f"pr {i}")
        for i in range(7)
    )
    snap = replace(
        snapshot,
        pull_requests=snapshot.pull_requests + stale,
        reviews=(Review("octo/api", False, NOW - timedelta(days=3), NOW - timedelta(days=2)),),
    )
    alert_svg = str(alerts.render(RenderContext(snap, profile, DARK)))
    assert "+2 more firing" in alert_svg and "WARNING" in alert_svg
    review_svg = str(reviews.render(RenderContext(snap, profile, DARK)))
    assert "24.0h" in review_svg and "peak 1/wk" in review_svg


def test_status_degrades_when_token_expires_soon(snapshot, profile):
    from dataclasses import replace

    soon = replace(snapshot, meta={"token_expires": "2026-10-20"})
    svg = str(status.render(RenderContext(soon, profile, DARK)))
    assert "DEGRADED" in svg and "expires in 5d" in svg
    assert "OPERATIONAL" in str(status.render(RenderContext(snapshot, profile, DARK)))


def test_record_cards_and_helpers(snapshot):
    from pulse import insights
    from pulse.render import churn, drift, records, servicemap

    cards = records.record_cards(insights.year_records(snapshot))
    assert len(cards) == 6
    assert records._minutes(0.5) == "30s" and records._minutes(30) == "30 min"
    assert records._minutes(180) == "3.0 h"
    assert churn.scaled(0, 10) == 0 and churn.scaled(10, 10) == churn.HALF
    assert servicemap.node_radius(0, 0) == servicemap.MIN_R
    assert len(servicemap.node_positions(4)) == 4
    bands = drift.band_paths(insights.language_drift(snapshot))
    assert all(d.startswith("M") and d.endswith("Z") for _, _, d in bands)
