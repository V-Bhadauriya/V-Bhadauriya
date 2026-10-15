"""Code churn as mirrored rx/tx bars: lines added above the axis, removed below."""

from __future__ import annotations

import math

from pulse import insights, metrics
from pulse.render.context import RenderContext
from pulse.render.svg import Markup, document, group, line, rect, text
from pulse.render.theme import FULL_W, PAD, panel, stylesheet

HEIGHT = 300
LEFT, RIGHT = 64, FULL_W - PAD - 8
MID = 148
HALF = 86  # pixel height of each side at the scale maximum


def scaled(value: int, peak: int) -> float:
    """Square-root scale so a single generated-code week doesn't flatten the rest."""
    if value <= 0 or peak <= 0:
        return 0.0
    return HALF * math.sqrt(value / peak)


def render(ctx: RenderContext) -> Markup:
    t = ctx.theme
    weeks = insights.weekly_churn(ctx.snapshot)
    peak = max((max(w.additions, w.deletions) for w in weeks), default=0)
    slot = (RIGHT - LEFT) / max(len(weeks), 1)
    bar_w = max(slot - 3, 2)
    bars = []
    for i, week in enumerate(weeks):
        x = LEFT + i * slot
        up, down = scaled(week.additions, peak), scaled(week.deletions, peak)
        wait = f"animation-delay:{0.2 + i * 0.015:.2f}s"
        if up:
            bars.append(
                rect(
                    x,
                    MID - up,
                    bar_w,
                    up,
                    rx=1.5,
                    fill=t.ok,
                    fill_opacity=0.85,
                    class_="growy",
                    style=wait,
                )
            )
        if down:
            bars.append(
                rect(
                    x,
                    MID + 1,
                    bar_w,
                    down,
                    rx=1.5,
                    fill=t.crit,
                    fill_opacity=0.75,
                    class_="grow-down",
                    style=wait,
                )
            )
    added = sum(w.additions for w in weeks)
    removed = sum(w.deletions for w in weeks)
    subtitle = f"rx +{metrics.compact_number(added)} · tx −{metrics.compact_number(removed)}"
    return document(
        FULL_W,
        HEIGHT,
        "Weekly code churn, lines added versus removed",
        stylesheet(
            t,
            ".grow-down{transform-box:fill-box;transform-origin:center top;"
            "animation:growy .8s cubic-bezier(.2,.7,.2,1) both;}",
        ),
        panel(t, FULL_W, HEIGHT, "Code churn · rx/tx per week", subtitle),
        _axis(ctx, peak, weeks, slot),
        *bars,
        _legend(ctx),
    )


def _axis(ctx: RenderContext, peak: int, weeks, slot: float) -> Markup:
    t = ctx.theme
    marks = [line(LEFT, MID, RIGHT, MID, stroke=t.border)]
    for frac in (1.0, 0.25):
        value = int(peak * frac)
        offset = scaled(value, peak)
        for sign, prefix in ((-1, "+"), (1, "−")):
            y = MID + sign * offset
            marks.append(line(LEFT, y, RIGHT, y, class_="s-grid", stroke_dasharray="2 4"))
            marks.append(
                text(
                    LEFT - 6,
                    y + 3,
                    f"{prefix}{metrics.compact_number(value)}",
                    class_="sm mut",
                    text_anchor="end",
                )
            )
    last_month = None
    for i, week in enumerate(weeks):
        if week.start.month != last_month:
            marks.append(
                text(LEFT + i * slot, MID + HALF + 22, f"{week.start:%b}", class_="sm mut")
            )
            last_month = week.start.month
    return group(*marks)


def _legend(ctx: RenderContext) -> Markup:
    t = ctx.theme
    y = HEIGHT - 12
    return group(
        rect(PAD, y - 9, 10, 10, rx=2, fill=t.ok),
        text(PAD + 16, y, "rx · lines added", class_="sm mut"),
        rect(PAD + 150, y - 9, 10, 10, rx=2, fill=t.crit),
        text(PAD + 166, y, "tx · lines removed", class_="sm mut"),
        text(FULL_W - PAD, y, "√ scale", class_="sm mut", text_anchor="end"),
    )
