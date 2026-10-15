"""Language drift: 100% stacked area of commit share by language, month by month."""

from __future__ import annotations

from pulse import insights
from pulse.render.context import RenderContext
from pulse.render.svg import Markup, circle, document, el, group, path, rect, text
from pulse.render.theme import FULL_W, PAD, panel, stylesheet

HEIGHT = 262
LEFT, RIGHT = 44, FULL_W - 150
TOP, BOTTOM = 54, HEIGHT - 34


def band_paths(drift: insights.Drift) -> list[tuple[str, str, str]]:
    """(language, color, svg path) for each stacked band, bottom to top."""
    months = len(drift.months)
    step = (RIGHT - LEFT) / max(months - 1, 1)
    xs = [LEFT + i * step for i in range(months)]
    base = [0.0] * months
    bands = []
    for name, color, shares in drift.series:
        top = [b + s for b, s in zip(base, shares, strict=True)]

        def y(v: float) -> float:
            return BOTTOM - (BOTTOM - TOP) * v

        upper = " L".join(f"{x:.1f},{y(v):.1f}" for x, v in zip(xs, top, strict=True))
        lower = " L".join(
            f"{x:.1f},{y(v):.1f}" for x, v in reversed(list(zip(xs, base, strict=True)))
        )
        bands.append((name, color, f"M{upper} L{lower} Z"))
        base = top
    return bands


def render(ctx: RenderContext) -> Markup:
    t = ctx.theme
    drift = insights.language_drift(ctx.snapshot)
    bands = band_paths(drift) if drift.series else []
    shapes = [
        path(d, fill=color, fill_opacity=0.78, stroke=t.panel, stroke_width=1)
        for _, color, d in bands
    ]
    return document(
        FULL_W,
        HEIGHT,
        "Language drift over the last 12 months",
        stylesheet(
            t,
            "@keyframes wipe{from{transform:scaleX(0)}}"
            ".wipe{transform-box:fill-box;transform-origin:left center;"
            "animation:wipe 1.6s cubic-bezier(.4,0,.2,1) both;}",
        ),
        el(
            "defs",
            None,
            el(
                "clipPath",
                {"id": "reveal"},
                rect(LEFT, TOP, RIGHT - LEFT, BOTTOM - TOP, class_="wipe"),
            ),
        ),
        panel(
            t, FULL_W, HEIGHT, "Language drift · share of commits", "12 months · by repo language"
        ),
        _grid(ctx, drift),
        group(*shapes, clip_path="url(#reveal)")
        if shapes
        else text(
            (LEFT + RIGHT) / 2,
            (TOP + BOTTOM) / 2,
            "no commits with language data yet",
            class_="md mut",
            text_anchor="middle",
        ),
        _legend(ctx, drift),
    )


def _grid(ctx: RenderContext, drift: insights.Drift) -> Markup:
    months = len(drift.months)
    step = (RIGHT - LEFT) / max(months - 1, 1)
    marks = []
    for frac in (0, 0.5, 1):
        y = BOTTOM - (BOTTOM - TOP) * frac
        marks.append(text(LEFT - 6, y + 3, f"{frac:.0%}", class_="sm mut", text_anchor="end"))
    for i, month in enumerate(drift.months):
        if i % 2 == 0 or i == months - 1:
            marks.append(
                text(
                    LEFT + i * step,
                    BOTTOM + 16,
                    f"{month:%b}",
                    class_="sm mut",
                    text_anchor="middle",
                )
            )
    return group(*marks)


def _legend(ctx: RenderContext, drift: insights.Drift) -> Markup:
    items = []
    for i, (name, color, shares) in enumerate(reversed(drift.series)):
        y = TOP + 10 + i * 22
        latest = shares[-1] if shares else 0.0
        items.append(
            group(
                circle(RIGHT + 24, y - 4, 5, fill=color),
                text(RIGHT + 36, y, name, class_="md"),
                text(FULL_W - PAD, y, f"{latest:.0%}", class_="sm mut", text_anchor="end"),
                class_="rise",
                style=f"animation-delay:{0.6 + i * 0.1:.2f}s",
            )
        )
    return group(*items, text(RIGHT + 24, BOTTOM + 16, "share this month", class_="sm mut"))
