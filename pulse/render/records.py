"""Year in review: personal records plus a monthly activity bar chart."""

from __future__ import annotations

from pulse import insights, metrics
from pulse.render.context import RenderContext
from pulse.render.svg import Markup, document, group, rect, text, truncate
from pulse.render.theme import FULL_W, PAD, panel, stylesheet

HEIGHT = 330
CARD_W = (FULL_W - 2 * PAD - 2 * 8) / 3
CARD_H = 56
CARDS_Y = 48
BARS_TOP, BARS_BOTTOM = 196, HEIGHT - 30


def record_cards(rec: insights.Records) -> tuple[tuple[str, str, str], ...]:
    def or_dash(value: object, fmt) -> str:
        return fmt(value) if value is not None else "—"

    return (
        ("LONGEST STREAK", f"{rec.longest_streak} days", "consecutive active days"),
        (
            "BUSIEST DAY",
            or_dash(rec.busiest_day, lambda d: f"{d[1]} events"),
            or_dash(rec.busiest_day, lambda d: f"{d[0]:%b %d, %Y}"),
        ),
        (
            "BUSIEST MONTH",
            or_dash(rec.busiest_month, lambda m: f"{m[1]:,} events"),
            or_dash(rec.busiest_month, lambda m: f"{m[0]:%B %Y}"),
        ),
        (
            "BIGGEST COMMIT",
            or_dash(rec.biggest_commit, lambda c: f"{metrics.compact_number(c[0])} lines"),
            or_dash(rec.biggest_commit, lambda c: truncate(c[1], 34)),
        ),
        (
            "FASTEST MERGE",
            or_dash(rec.fastest_merge_minutes, _minutes),
            "PR opened → merged",
        ),
        (
            "TOP SERVICE",
            or_dash(rec.top_service, lambda s: f"{s[1]:,} events"),
            or_dash(rec.top_service, lambda s: truncate(s[0], 34)),
        ),
    )


def _minutes(value: float) -> str:
    if value < 1:
        return f"{value * 60:.0f}s"
    if value < 120:
        return f"{value:.0f} min"
    return f"{value / 60:.1f} h"


def render(ctx: RenderContext) -> Markup:
    t = ctx.theme
    rec = insights.year_records(ctx.snapshot)
    cards = [
        _card(ctx, PAD + (i % 3) * (CARD_W + 8), CARDS_Y + (i // 3) * (CARD_H + 8), c, i)
        for i, c in enumerate(record_cards(rec))
    ]
    return document(
        FULL_W,
        HEIGHT,
        "Year in review records",
        stylesheet(t),
        panel(t, FULL_W, HEIGHT, "Year in review · personal bests", "last 12 months"),
        *cards,
        _monthly(ctx, rec.monthly),
    )


def _card(ctx: RenderContext, x: float, y: float, card, index: int) -> Markup:
    t = ctx.theme
    label, value, hint = card
    accent = (t.accent, t.accent2, t.ok, t.warn, t.accent, t.accent2)[index % 6]
    return group(
        rect(x, y, CARD_W, CARD_H, rx=8, fill=t.bg, stroke=t.border, fill_opacity=0.55),
        rect(x, y + 12, 2, CARD_H - 24, fill=accent),
        text(x + 12, y + 17, label, class_="sm mut", letter_spacing="0.1em"),
        text(x + 12, y + 38, value, font_size=17, font_weight=700),
        text(x + 12, y + 50, hint, class_="mut", font_size=8.5),
        class_="rise",
        style=f"animation-delay:{0.1 + index * 0.08:.2f}s",
    )


def _monthly(ctx: RenderContext, monthly) -> Markup:
    t = ctx.theme
    peak = max((c for _, c in monthly), default=0)
    slot = (FULL_W - 2 * PAD) / max(len(monthly), 1)
    height = BARS_BOTTOM - BARS_TOP
    parts = [text(PAD, BARS_TOP - 10, "EVENTS PER MONTH", class_="sm mut", letter_spacing="0.1em")]
    for i, (month, count) in enumerate(monthly):
        x = PAD + i * slot
        h = height * count / peak if peak else 0
        if h:
            parts.append(
                rect(
                    x + 6,
                    BARS_BOTTOM - h,
                    slot - 12,
                    h,
                    rx=3,
                    fill=t.accent,
                    fill_opacity=0.35 + 0.65 * count / peak,
                    class_="growy",
                    style=f"animation-delay:{0.5 + i * 0.06:.2f}s",
                )
            )
            parts.append(
                text(
                    x + slot / 2,
                    BARS_BOTTOM - h - 5,
                    metrics.compact_number(count),
                    class_="sm mut",
                    text_anchor="middle",
                )
            )
        parts.append(
            text(
                x + slot / 2, BARS_BOTTOM + 15, f"{month:%b}", class_="sm mut", text_anchor="middle"
            )
        )
    return group(*parts)
