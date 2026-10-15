"""Full-year activity panel: headline counters above a daily contribution grid."""

from __future__ import annotations

from pulse import metrics
from pulse.render.context import RenderContext
from pulse.render.heatmap import intensity
from pulse.render.svg import Markup, document, group, rect, text
from pulse.render.theme import FULL_W, PAD, panel, stylesheet

HEIGHT = 276
CELL, GAP = 12, 3
GRID_X, GRID_Y = 46, 140
COUNTER_Y, COUNTER_H = 48, 58


def render(ctx: RenderContext) -> Markup:
    t = ctx.theme
    totals = metrics.activity_totals(ctx.snapshot)
    weeks = metrics.calendar_weeks(ctx.snapshot)
    return document(
        FULL_W,
        HEIGHT,
        "Activity over the last 365 days",
        stylesheet(t),
        panel(t, FULL_W, HEIGHT, "Activity · last 365 days", "commits + PRs per day · UTC"),
        _counters(ctx, totals),
        _grid(ctx, weeks),
        _footer(ctx, totals),
    )


def counter_cells(totals: metrics.Totals) -> tuple[tuple[str, str, str], ...]:
    churn = (
        f"+{metrics.compact_number(totals.additions)} −{metrics.compact_number(totals.deletions)}"
    )
    return (
        ("COMMITS", f"{totals.commits:,}", "on default branches"),
        ("PRS OPENED", f"{totals.prs_opened:,}", "authored"),
        ("PRS MERGED", f"{totals.prs_merged:,}", "shipped"),
        ("LINES", churn, "added / removed"),
        ("REPOS", f"{totals.repos:,}", "touched"),
        ("ACTIVE DAYS", f"{totals.active_days}", "of 365"),
    )


def _counters(ctx: RenderContext, totals: metrics.Totals) -> Markup:
    t = ctx.theme
    cells = counter_cells(totals)
    width = (FULL_W - 2 * PAD - (len(cells) - 1) * 8) / len(cells)
    parts = []
    for i, (label, value, hint) in enumerate(cells):
        x = PAD + i * (width + 8)
        parts.append(
            group(
                rect(
                    x,
                    COUNTER_Y,
                    width,
                    COUNTER_H,
                    rx=8,
                    fill=t.bg,
                    stroke=t.border,
                    fill_opacity=0.55,
                ),
                rect(x, COUNTER_Y + 12, 2, COUNTER_H - 24, fill=t.accent2 if i % 2 else t.accent),
                text(x + 12, COUNTER_Y + 17, label, class_="sm mut", letter_spacing="0.1em"),
                text(
                    x + 12,
                    COUNTER_Y + 39,
                    value,
                    font_size=18 if len(value) < 10 else 14,
                    font_weight=700,
                ),
                text(x + 12, COUNTER_Y + 51, hint, class_="mut", font_size=8.5),
                class_="rise",
                style=f"animation-delay:{0.1 + i * 0.08:.2f}s",
            )
        )
    return group(*parts)


def _grid(ctx: RenderContext, weeks) -> Markup:
    t = ctx.theme
    peak = max((d[1] for week in weeks for d in week if d), default=0)
    cells, months, last_month = [], [], None
    for col, week in enumerate(weeks):
        x = GRID_X + col * (CELL + GAP)
        first = next((d for d in week if d), None)
        if first and first[0].month != last_month and first[0].day <= 7:
            months.append(text(x, GRID_Y - 8, f"{first[0]:%b}", class_="sm mut"))
            last_month = first[0].month
        for row, day in enumerate(week):
            if day is None:
                continue
            alpha = intensity(day[1], peak)
            cells.append(
                rect(
                    x,
                    GRID_Y + row * (CELL + GAP),
                    CELL,
                    CELL,
                    rx=2.5,
                    fill=t.accent if alpha else t.grid,
                    fill_opacity=f"{alpha:.2f}" if alpha else None,
                    class_="fade",
                    style=f"animation-delay:{0.4 + col * 0.022 + row * 0.03:.2f}s",
                )
            )
    labels = (
        text(
            GRID_X - 8,
            GRID_Y + row * (CELL + GAP) + CELL - 2,
            name,
            class_="sm mut",
            text_anchor="end",
        )
        for row, name in ((0, "Mon"), (2, "Wed"), (4, "Fri"), (6, "Sun"))
    )
    return group(*months, *labels, *cells)


def _footer(ctx: RenderContext, totals: metrics.Totals) -> Markup:
    t = ctx.theme
    y = HEIGHT - 14
    busiest = (
        f"busiest day: {totals.busiest_day[0]:%b %d, %Y} · {totals.busiest_day[1]} events"
        if totals.busiest_day
        else "no activity recorded yet"
    )
    x = FULL_W - PAD - 5 * 14
    swatches = (
        rect(
            x + i * 14,
            y - 10,
            CELL - 1,
            CELL - 1,
            rx=2,
            fill=t.accent if a else t.grid,
            fill_opacity=a or None,
        )
        for i, a in enumerate((0, 0.25, 0.5, 0.75, 1.0))
    )
    return group(
        text(PAD, y, busiest, class_="sm mut"),
        text(x - 6, y, "less", class_="sm mut", text_anchor="end"),
        *swatches,
    )
