"""Career history rendered as `helm history` (shown only when configured)."""

from __future__ import annotations

from pulse.render.context import RenderContext
from pulse.render.svg import Markup, document, group, rect, text, truncate
from pulse.render.theme import FULL_W, PAD, panel, stylesheet

TOP = 98
ROW_H = 22
COLS = (("REV", PAD), ("UPDATED", 64), ("STATUS", 236), ("CHART", 344), ("DESCRIPTION", 540))


def height_for(rows: int) -> int:
    return TOP + max(rows, 1) * ROW_H + 30


def render(ctx: RenderContext) -> Markup:
    t = ctx.theme
    roles = ctx.profile.experience  # listed oldest first in profile.yml
    height = height_for(len(roles))
    rows = []
    for i, role in enumerate(roles):
        y = TOP + i * ROW_H
        current = role.end is None
        description = f"{role.title}" + (f" — {role.summary}" if role.summary else "")
        rows.append(
            group(
                text(COLS[0][1], y, i + 1, class_="md mut"),
                text(COLS[1][1], y, f"{role.start} → {role.end or 'now'}", class_="md mut"),
                text(
                    COLS[2][1],
                    y,
                    "deployed" if current else "superseded",
                    class_="md",
                    fill=t.ok if current else t.muted,
                    font_weight=700 if current else None,
                ),
                text(COLS[3][1], y, truncate(role.org, 26), class_="md acc"),
                text(COLS[4][1], y, truncate(description, 41), class_="md"),
                class_="rise",
                style=f"animation-delay:{0.3 + i * 0.12:.2f}s",
            )
        )
    namespace = ctx.profile.handle.split(".")[0]
    cursor_y = TOP + max(len(roles), 1) * ROW_H + 6
    return document(
        FULL_W,
        height,
        "Career history",
        stylesheet(t),
        panel(t, FULL_W, height, "Experience · release history", f"{len(roles)} revisions"),
        text(PAD, 58, "$", class_="md acc"),
        text(PAD + 14, 58, f"helm history {namespace}", class_="md"),
        group(*(text(x, 80, name, class_="sm mut", letter_spacing="0.06em") for name, x in COLS)),
        *rows,
        text(PAD, cursor_y, "$", class_="md acc"),
        rect(PAD + 14, cursor_y - 10, 7, 13, fill=t.accent, class_="blink"),
    )
