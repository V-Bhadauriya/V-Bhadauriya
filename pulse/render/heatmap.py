"""Hour-of-day x weekday activity heatmap with a scanning sweep."""

from __future__ import annotations

from pulse import metrics
from pulse.render.context import RenderContext
from pulse.render.svg import Markup, document, el, group, rect, text
from pulse.render.theme import HALF_H, HALF_W, PAD, panel, stylesheet

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
GRID_X, GRID_Y = 50, 50
CELL_W, CELL_H, GAP = 13.5, 17, 2

SWEEP_PX = 24 * (CELL_W + GAP)
EXTRA_CSS = f"""
@keyframes sweep{{from{{transform:translateX(0)}}to{{transform:translateX({SWEEP_PX:.0f}px)}}}}
.sweep{{animation:sweep 5.5s linear infinite;}}
"""


def intensity(value: int, peak: int) -> float:
    """Perceptual opacity for a cell; 0 means empty."""
    if value <= 0 or peak <= 0:
        return 0.0
    return 0.18 + 0.82 * (value / peak) ** 0.6


def render(ctx: RenderContext) -> Markup:
    t = ctx.theme
    matrix = metrics.heatmap(ctx.snapshot, ctx.profile.tz)
    peak = max((v for row in matrix for v in row), default=0)
    total = sum(v for row in matrix for v in row)
    tz_abbr = ctx.snapshot.fetched_at.astimezone(ctx.profile.tz).strftime("%Z")
    grid_w = 24 * (CELL_W + GAP)
    grid_h = 7 * (CELL_H + GAP)
    return document(
        HALF_W,
        HALF_H,
        "Activity heatmap by hour and weekday",
        stylesheet(t, EXTRA_CSS),
        el(
            "defs",
            None,
            el(
                "linearGradient",
                {"id": "beam", "x1": "0", "x2": "1"},
                el("stop", {"offset": "0", "stop-color": t.accent, "stop-opacity": "0"}),
                el("stop", {"offset": "1", "stop-color": t.accent, "stop-opacity": "0.45"}),
            ),
            el("clipPath", {"id": "gridclip"}, rect(GRID_X, GRID_Y, grid_w, grid_h)),
        ),
        panel(t, HALF_W, HALF_H, "Latency map · hour × day", f"{total:,} events · {tz_abbr}"),
        _labels(),
        _cells(ctx, matrix, peak),
        group(
            rect(GRID_X - 30, GRID_Y, 30, grid_h, fill="url(#beam)", class_="sweep"),
            clip_path="url(#gridclip)",
        ),
        text(PAD, HALF_H - 14, _summary(matrix), class_="sm mut"),
        _legend(ctx),
    )


def _labels() -> Markup:
    days = (
        text(
            GRID_X - 8,
            GRID_Y + i * (CELL_H + GAP) + CELL_H - 5,
            d,
            class_="sm mut",
            text_anchor="end",
        )
        for i, d in enumerate(DAYS)
    )
    hours = (
        text(
            GRID_X + h * (CELL_W + GAP),
            GRID_Y + 7 * (CELL_H + GAP) + 12,
            f"{h:02d}",
            class_="sm mut",
        )
        for h in (0, 6, 12, 18)
    )
    return group(*days, *hours)


def _cells(ctx: RenderContext, matrix, peak: int) -> Markup:
    t = ctx.theme
    cells = []
    for d, row in enumerate(matrix):
        for h, value in enumerate(row):
            alpha = intensity(value, peak)
            cells.append(
                rect(
                    GRID_X + h * (CELL_W + GAP),
                    GRID_Y + d * (CELL_H + GAP),
                    CELL_W,
                    CELL_H,
                    rx=3,
                    fill=t.accent if alpha else t.grid,
                    fill_opacity=f"{alpha:.2f}" if alpha else None,
                    class_="fade",
                    style=f"animation-delay:{h * 0.035 + d * 0.05:.2f}s",
                )
            )
    return group(*cells)


def _summary(matrix) -> str:
    flat = [(v, d, h) for d, row in enumerate(matrix) for h, v in enumerate(row)]
    if not flat or max(flat)[0] == 0:
        return "no activity recorded yet"
    _, day, hour = max(flat)
    hourly = [sum(matrix[d][h] for d in range(7)) for h in range(24)]
    quiet = min(range(24), key=lambda h: (hourly[h], h))
    return f"hot: {DAYS[day]} {hour:02d}:00  ·  quietest hour: {quiet:02d}:00"


def _legend(ctx: RenderContext) -> Markup:
    t = ctx.theme
    x = HALF_W - PAD - 5 * 12
    swatches = (
        rect(
            x + i * 12,
            HALF_H - 24,
            10,
            10,
            rx=2,
            fill=t.accent if a else t.grid,
            fill_opacity=a or None,
        )
        for i, a in enumerate((0, 0.25, 0.5, 0.75, 1.0))
    )
    return group(text(x - 6, HALF_H - 15, "less", class_="sm mut", text_anchor="end"), *swatches)
