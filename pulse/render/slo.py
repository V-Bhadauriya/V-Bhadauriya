"""SLO panel: availability, throughput, MTTR and merge-rate gauges."""

from __future__ import annotations

import math
from dataclasses import dataclass

from pulse import metrics
from pulse.render.context import RenderContext
from pulse.render.svg import Markup, circle, document, el, group, line, path, text
from pulse.render.theme import FULL_W, panel, status_color, stylesheet

HEIGHT = 250
THROUGHPUT_TARGET = 40.0  # events per week that counts as a "full" gauge
MTTR_BUDGET_H = 24.0  # merges slower than this empty the gauge
SWEEP_DEG = 240
RADIUS = 52
CY = 140

EXTRA_CSS = """
@keyframes needle{from{transform:rotate(-120deg)}}
.needle{animation:needle 2s cubic-bezier(.3,1.4,.4,1) both;}
"""


@dataclass(frozen=True)
class Gauge:
    label: str
    value: str
    hint: str
    ratio: float  # 0..1 fill
    health: float  # 0..1, higher is healthier


def gauges(ctx: RenderContext) -> tuple[Gauge, ...]:
    snap = ctx.snapshot
    avail = metrics.availability(snap)
    thru = metrics.throughput(snap)
    thru_ratio = min(thru / THROUGHPUT_TARGET, 1.0)
    mttr = metrics.mttr_hours(snap)
    mttr_ratio = 0.0 if mttr is None else max(0.0, 1 - mttr / MTTR_BUDGET_H)
    merge = metrics.merge_rate(snap)
    return (
        Gauge("AVAILABILITY", f"{avail:.0%}", "active days · 30d", avail, avail),
        Gauge("THROUGHPUT", f"{thru:.0f}/wk", "events · 12w avg", thru_ratio, thru_ratio),
        Gauge(
            "MTTR",
            "n/a" if mttr is None else format_hours(mttr),
            "PR open → merge p50",
            mttr_ratio,
            mttr_ratio,
        ),
        Gauge(
            "MERGE RATE",
            "n/a" if merge is None else f"{merge:.0%}",
            "merged / closed PRs",
            merge or 0.0,
            merge or 0.0,
        ),
    )


def format_hours(hours: float) -> str:
    if hours < 1:
        return f"{hours * 60:.0f}m"
    if hours < 48:
        return f"{hours:.1f}h"
    return f"{hours / 24:.0f}d"


def arc_path(cx: float, cy: float, r: float) -> str:
    """Full 240° gauge track, starting bottom-left and sweeping clockwise."""
    start, end = math.radians(150), math.radians(150 + SWEEP_DEG)
    x1, y1 = cx + r * math.cos(start), cy + r * math.sin(start)
    x2, y2 = cx + r * math.cos(end), cy + r * math.sin(end)
    return f"M{x1:.2f},{y1:.2f} A{r},{r} 0 1 1 {x2:.2f},{y2:.2f}"


def render(ctx: RenderContext) -> Markup:
    t = ctx.theme
    snap = ctx.snapshot
    items = gauges(ctx)
    centers = tuple(FULL_W * (2 * i + 1) / (2 * len(items)) for i in range(len(items)))
    footer = f"PRs {len(snap.pull_requests):,}  ·  commits {len(snap.commits):,}"
    return document(
        FULL_W,
        HEIGHT,
        "Service level objectives",
        stylesheet(t, EXTRA_CSS),
        panel(t, FULL_W, HEIGHT, "SLO · error budget", "rolling windows"),
        *(_gauge(ctx, cx, g, i) for i, (cx, g) in enumerate(zip(centers, items, strict=True))),
        text(FULL_W / 2, HEIGHT - 12, footer, class_="sm mut", text_anchor="middle"),
    )


def _gauge(ctx: RenderContext, cx: float, gauge: Gauge, index: int) -> Markup:
    t = ctx.theme
    color = status_color(t, gauge.health)
    track = arc_path(cx, CY, RADIUS)
    ticks = (
        line(
            cx + (RADIUS - 15) * math.cos(math.radians(a)),
            CY + (RADIUS - 15) * math.sin(math.radians(a)),
            cx + (RADIUS - 10) * math.cos(math.radians(a)),
            CY + (RADIUS - 10) * math.sin(math.radians(a)),
            class_="s-mut",
            stroke_width=1,
            opacity=0.6,
        )
        for a in range(150, 150 + SWEEP_DEG + 1, 30)
    )
    angle = -SWEEP_DEG / 2 + SWEEP_DEG * gauge.ratio
    wait = f"animation-delay:{0.2 + index * 0.2:.2f}s"
    return group(
        path(track, fill="none", stroke=t.grid, stroke_width=9, stroke_linecap="round"),
        path(
            track,
            fill="none",
            stroke=color,
            stroke_width=9,
            stroke_linecap="round",
            pathLength=1,
            class_="draw",
            style=f"stroke-dashoffset:{1 - gauge.ratio:.3f};{wait}",
        ),
        *ticks,
        el(
            "g",
            {
                "class": "needle",
                "style": f"transform-origin:{cx:.1f}px {CY}px;transform:rotate({angle:.1f}deg);"
                f"{wait}",
            },
            line(
                cx, CY, cx, CY - RADIUS + 18, stroke=t.text, stroke_width=2, stroke_linecap="round"
            ),
        ),
        circle(cx, CY, 4.5, fill=t.bg, stroke=t.text, stroke_width=1.5),
        text(cx, CY + 40, gauge.value, class_="lg", text_anchor="middle", fill=color),
        text(cx, 66, gauge.label, class_="sm mut", text_anchor="middle", letter_spacing="0.12em"),
        text(cx, CY + 56, gauge.hint, class_="mut", font_size=9, text_anchor="middle"),
    )
