"""SLO panel: availability, throughput and MTTR gauges."""

from __future__ import annotations

import math
from dataclasses import dataclass

from pulse import metrics
from pulse.render.context import RenderContext
from pulse.render.svg import Markup, circle, document, el, group, line, path, text
from pulse.render.theme import HALF_H, HALF_W, panel, status_color, stylesheet

THROUGHPUT_TARGET = 40.0  # events per week that counts as a "full" gauge
MTTR_BUDGET_H = 24.0  # merges slower than this empty the gauge
SWEEP_DEG = 240
RADIUS = 44
CY = 128

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
    mttr = metrics.mttr_hours(snap)
    mttr_ratio = 0.0 if mttr is None else max(0.0, 1 - mttr / MTTR_BUDGET_H)
    return (
        Gauge("AVAILABILITY", f"{avail:.0%}", "active days · 30d", avail, avail),
        Gauge(
            "THROUGHPUT",
            f"{thru:.0f}/wk",
            "events · 12w avg",
            min(thru / THROUGHPUT_TARGET, 1.0),
            min(thru / THROUGHPUT_TARGET, 1.0),
        ),
        Gauge(
            "MTTR",
            "n/a" if mttr is None else format_hours(mttr),
            "PR open → merge p50",
            mttr_ratio,
            mttr_ratio,
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
    merge = metrics.merge_rate(snap)
    centers = (HALF_W * 0.18, HALF_W * 0.5, HALF_W * 0.82)
    footer = (
        f"merge rate {merge:.0%}" if merge is not None else "merge rate n/a",
        f"PRs {len(snap.pull_requests):,}",
        f"commits {len(snap.commits):,}",
    )
    return document(
        HALF_W,
        HALF_H,
        "Service level objectives",
        stylesheet(t, EXTRA_CSS),
        panel(t, HALF_W, HALF_H, "SLO · error budget", "rolling windows"),
        *(
            _gauge(ctx, cx, g, i)
            for i, (cx, g) in enumerate(zip(centers, gauges(ctx), strict=True))
        ),
        text(HALF_W / 2, HALF_H - 14, "  ·  ".join(footer), class_="sm mut", text_anchor="middle"),
    )


def _gauge(ctx: RenderContext, cx: float, gauge: Gauge, index: int) -> Markup:
    t = ctx.theme
    color = status_color(t, gauge.health)
    track = arc_path(cx, CY, RADIUS)
    ticks = (
        line(
            cx + (RADIUS - 13) * math.cos(math.radians(a)),
            CY + (RADIUS - 13) * math.sin(math.radians(a)),
            cx + (RADIUS - 9) * math.cos(math.radians(a)),
            CY + (RADIUS - 9) * math.sin(math.radians(a)),
            class_="s-mut",
            stroke_width=1,
            opacity=0.6,
        )
        for a in range(150, 150 + SWEEP_DEG + 1, 30)
    )
    angle = -SWEEP_DEG / 2 + SWEEP_DEG * gauge.ratio
    wait = f"animation-delay:{0.2 + index * 0.2:.2f}s"
    return group(
        path(track, fill="none", stroke=t.grid, stroke_width=8, stroke_linecap="round"),
        path(
            track,
            fill="none",
            stroke=color,
            stroke_width=8,
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
                cx, CY, cx, CY - RADIUS + 16, stroke=t.text, stroke_width=2, stroke_linecap="round"
            ),
        ),
        circle(cx, CY, 4, fill=t.bg, stroke=t.text, stroke_width=1.5),
        text(cx, CY + 34, gauge.value, class_="lg", text_anchor="middle", fill=color),
        text(cx, 64, gauge.label, class_="sm mut", text_anchor="middle", letter_spacing="0.12em"),
        text(cx, CY + 50, gauge.hint, class_="mut", font_size=8.5, text_anchor="middle"),
    )
