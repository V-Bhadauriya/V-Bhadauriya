"""`kubectl top`-style language resource usage."""

from __future__ import annotations

from pulse import metrics
from pulse.render.context import RenderContext
from pulse.render.svg import Markup, circle, document, group, rect, text, truncate
from pulse.render.theme import HALF_H, HALF_W, PAD, panel, stylesheet

SEGMENTS = 22
SEG_W, SEG_GAP = 8, 2
BAR_X = 128
ROW_Y0, ROW_H = 76, 21


def lit_segments(share: float, top_share: float) -> int:
    if top_share <= 0 or share <= 0:
        return 0
    return max(1, round(SEGMENTS * share / top_share))


def render(ctx: RenderContext) -> Markup:
    t = ctx.theme
    shares = metrics.language_shares(ctx.snapshot)
    top = max((s.share for s in shares), default=0.0)
    rows = [_row(ctx, s, i, top) for i, s in enumerate(shares)] or [
        text(HALF_W / 2, 130, "no language data", class_="md mut", text_anchor="middle")
    ]
    return document(
        HALF_W,
        HALF_H,
        "Language resource usage",
        stylesheet(t),
        panel(t, HALF_W, HALF_H, "kubectl top lang", "bytes × recency · t½ 180d"),
        text(PAD, 56, "NAME", class_="sm mut", letter_spacing="0.1em"),
        text(BAR_X, 56, "USAGE", class_="sm mut", letter_spacing="0.1em"),
        text(HALF_W - PAD, 56, "SHARE", class_="sm mut", letter_spacing="0.1em", text_anchor="end"),
        *rows,
    )


def _row(ctx: RenderContext, share: metrics.LanguageShare, index: int, top: float) -> Markup:
    t = ctx.theme
    y = ROW_Y0 + index * ROW_H
    lit = lit_segments(share.share, top)
    segments = (
        rect(
            BAR_X + s * (SEG_W + SEG_GAP),
            y - 9,
            SEG_W,
            11,
            rx=1.5,
            fill=share.color if s < lit else t.grid,
            class_="fade" if s < lit else None,
            style=f"animation-delay:{0.2 + index * 0.1 + s * 0.04:.2f}s" if s < lit else None,
        )
        for s in range(SEGMENTS)
    )
    return group(
        circle(PAD + 4, y - 3.5, 4, fill=share.color),
        text(PAD + 14, y, truncate(share.name, 13), class_="md"),
        *segments,
        text(HALF_W - PAD, y, f"{share.share:.1%}", class_="md", text_anchor="end"),
        class_="rise",
        style=f"animation-delay:{index * 0.1:.2f}s",
    )
