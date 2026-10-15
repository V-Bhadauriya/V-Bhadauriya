"""Toolchain panel: the hand-curated stack from profile.yml as grouped, wrapping chips."""

from __future__ import annotations

from pulse.config import StackGroup
from pulse.render.context import RenderContext
from pulse.render.svg import Markup, document, group, rect, text
from pulse.render.theme import FULL_W, HEADER_H, PAD, Theme, panel, stylesheet

LABEL_X = PAD
CHIPS_X = 186
CHIPS_RIGHT = FULL_W - PAD
CHAR_W = 7.23  # advance of a 12px monospace glyph
CHIP_H, CHIP_GAP, LINE_H = 22, 8, 30
TOP = HEADER_H + 18
BOTTOM_PAD = 10


def chip_width(label: str) -> float:
    return len(label) * CHAR_W + 20


def layout(items: tuple[str, ...]) -> list[list[tuple[str, float, float]]]:
    """Greedy line wrapping: rows of (label, x, width) that fit between CHIPS_X and the edge."""
    lines: list[list[tuple[str, float, float]]] = [[]]
    x: float = CHIPS_X
    for item in items:
        width = chip_width(item)
        if lines[-1] and x + width > CHIPS_RIGHT:
            lines.append([])
            x = CHIPS_X
        lines[-1].append((item, x, width))
        x += width + CHIP_GAP
    return lines


def height_for(groups: tuple[StackGroup, ...]) -> int:
    rows = sum(len(layout(g.items)) for g in groups) or 1
    return int(TOP + rows * LINE_H + BOTTOM_PAD)


def _palette(theme: Theme) -> tuple[str, ...]:
    return (theme.accent, theme.accent2, theme.ok, theme.warn, theme.crit, theme.text)


def render(ctx: RenderContext) -> Markup:
    t = ctx.theme
    groups = ctx.profile.stack
    height = height_for(groups)
    total = sum(len(g.items) for g in groups)
    body: list[Markup] = []
    y = TOP
    order = 0
    for index, grp in enumerate(groups):
        color = _palette(t)[index % len(_palette(t))]
        lines = layout(grp.items)
        if grp.label:
            body.append(
                text(LABEL_X, y + 15, grp.label.upper(), class_="sm mut", letter_spacing="0.1em")
            )
        for line_items in lines:
            for label, x, width in line_items:
                body.append(_chip(label, x, y, width, color, order))
                order += 1
            y += LINE_H
    return document(
        FULL_W,
        height,
        "Toolchain",
        stylesheet(t),
        panel(t, FULL_W, height, "Toolchain · helm list", f"{total} tools · {len(groups)} groups"),
        *body,
    )


def _chip(label: str, x: float, y: float, width: float, color: str, order: int) -> Markup:
    return group(
        rect(
            x,
            y,
            width,
            CHIP_H,
            rx=11,
            fill=color,
            fill_opacity=0.12,
            stroke=color,
            stroke_opacity=0.55,
        ),
        text(x + 10, y + 15, label, class_="md"),
        class_="rise",
        style=f"animation-delay:{0.15 + order * 0.025:.2f}s",
    )
