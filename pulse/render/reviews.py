"""Code review panel: reviews given to teammates and how fast you pick them up."""

from __future__ import annotations

from pulse import insights
from pulse.render.context import RenderContext
from pulse.render.slo import format_hours
from pulse.render.svg import Markup, document, group, rect, text
from pulse.render.theme import FULL_W, PAD, panel, stylesheet

HEIGHT = 200
CARD_Y, CARD_H = 50, 58
BARS_TOP, BARS_BOTTOM = 128, HEIGHT - 26


def render(ctx: RenderContext) -> Markup:
    t = ctx.theme
    stats = insights.review_stats(ctx.snapshot)
    cards = (
        ("REVIEWS GIVEN", f"{stats.count:,}", "PRs by others · 365d"),
        ("FIRST RESPONSE", _hours(stats.median_hours), "p50 · PR open → your review"),
        ("SLOW TAIL", _hours(stats.p90_hours), "p90 response time"),
        ("REPOS REVIEWED", f"{stats.repos}", "distinct services"),
    )
    width = (FULL_W - 2 * PAD - 3 * 8) / 4
    return document(
        FULL_W,
        HEIGHT,
        "Code review activity",
        stylesheet(t),
        panel(t, FULL_W, HEIGHT, "Code review · peer approvals", "last 26 weeks"),
        *(_card(ctx, PAD + i * (width + 8), width, c, i) for i, c in enumerate(cards)),
        _bars(ctx, stats.weekly),
    )


def _hours(value: float | None) -> str:
    return "n/a" if value is None else format_hours(value)


def _card(ctx: RenderContext, x: float, width: float, card, index: int) -> Markup:
    t = ctx.theme
    label, value, hint = card
    return group(
        rect(x, CARD_Y, width, CARD_H, rx=8, fill=t.bg, stroke=t.border, fill_opacity=0.55),
        rect(x, CARD_Y + 12, 2, CARD_H - 24, fill=t.accent2 if index % 2 else t.accent),
        text(x + 12, CARD_Y + 17, label, class_="sm mut", letter_spacing="0.1em"),
        text(x + 12, CARD_Y + 39, value, font_size=18, font_weight=700),
        text(x + 12, CARD_Y + 51, hint, class_="mut", font_size=8.5),
        class_="rise",
        style=f"animation-delay:{0.1 + index * 0.08:.2f}s",
    )


def _bars(ctx: RenderContext, weekly: tuple[int, ...]) -> Markup:
    t = ctx.theme
    if not any(weekly):
        return text(
            FULL_W / 2,
            (BARS_TOP + BARS_BOTTOM) / 2 + 4,
            "no reviews recorded in this window",
            class_="sm mut",
            text_anchor="middle",
        )
    peak = max(weekly)
    slot = (FULL_W - 2 * PAD) / len(weekly)
    height = BARS_BOTTOM - BARS_TOP
    bars = []
    for i, count in enumerate(weekly):
        h = max(height * count / peak, 1.5 if count else 0)
        if h:
            bars.append(
                rect(
                    PAD + i * slot,
                    BARS_BOTTOM - h,
                    slot - 4,
                    h,
                    rx=2,
                    fill=t.accent2,
                    fill_opacity=0.75,
                    class_="growy",
                    style=f"animation-delay:{0.3 + i * 0.02:.2f}s",
                )
            )
    return group(
        *bars,
        text(PAD, HEIGHT - 10, "reviews per week", class_="sm mut"),
        text(FULL_W - PAD, HEIGHT - 10, f"peak {peak}/wk", class_="sm mut", text_anchor="end"),
    )
