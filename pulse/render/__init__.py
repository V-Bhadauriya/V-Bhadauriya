"""Panel registry: what gets rendered, in which order, and when."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pulse.config import Profile
from pulse.render import (
    activity,
    alerts,
    certs,
    churn,
    deploylog,
    drift,
    experience,
    featured,
    heatmap,
    pods,
    records,
    resources,
    reviews,
    servicemap,
    slo,
    status,
    timeseries,
    toolchain,
    trace,
)
from pulse.render.context import RenderContext
from pulse.render.svg import Markup

Renderer = Callable[[RenderContext], Markup]


def _always(_profile: Profile) -> bool:
    return True


@dataclass(frozen=True)
class PanelSpec:
    name: str
    render: Renderer
    alt: str
    enabled: Callable[[Profile], bool] = _always


SPECS: tuple[PanelSpec, ...] = (
    PanelSpec("status", status.render, "Live status banner"),
    PanelSpec("activity", activity.render, "Commits, pull requests and daily activity, 365 days"),
    PanelSpec("toolchain", toolchain.render, "Toolchain: languages, ML, MLOps, LLM, infra"),
    PanelSpec("servicemap", servicemap.render, "Service map of active repositories"),
    PanelSpec("deploylog", deploylog.render, "Live deploy log of commits and pull requests"),
    PanelSpec("slo", slo.render, "SLO gauges: availability, throughput, MTTR, merge rate"),
    PanelSpec("alerts", alerts.render, "Alerts for long-open pull requests"),
    PanelSpec("reviews", reviews.render, "Code review activity"),
    PanelSpec("timeseries", timeseries.render, "Weekly activity time series"),
    PanelSpec("churn", churn.render, "Weekly code churn, lines added and removed"),
    PanelSpec("heatmap", heatmap.render, "Activity heatmap by hour and weekday"),
    PanelSpec("trace", trace.render, "Trace waterfall of the last 14 days"),
    PanelSpec("drift", drift.render, "Language drift over 12 months"),
    PanelSpec("resources", resources.render, "Language usage"),
    PanelSpec("records", records.render, "Year in review records"),
    PanelSpec("featured", featured.render, "Featured public projects"),
    PanelSpec("pods", pods.render, "Public repositories as pods"),
    PanelSpec("experience", experience.render, "Career history", lambda p: bool(p.experience)),
    PanelSpec("certs", certs.render, "Certifications", lambda p: bool(p.certifications)),
)

PANELS: dict[str, Renderer] = {spec.name: spec.render for spec in SPECS}
HERO = ("status", "activity")


def enabled_specs(profile: Profile) -> tuple[PanelSpec, ...]:
    return tuple(spec for spec in SPECS if spec.enabled(profile))
