"""Featured public projects as cards with live stats."""

from __future__ import annotations

import textwrap

from pulse import insights, metrics
from pulse.render.context import RenderContext
from pulse.render.svg import Markup, circle, document, group, rect, text, truncate
from pulse.render.theme import FULL_W, PAD, panel, stylesheet

CARD_W = (FULL_W - 2 * PAD - 10) / 2
CARD_H = 112
TOP = 48
DESC_CHARS = 52


def height_for(count: int) -> int:
    rows = max((count + 1) // 2, 1)
    return int(TOP + rows * (CARD_H + 10) + 6)


def render(ctx: RenderContext) -> Markup:
    t = ctx.theme
    items = insights.featured_repos(ctx.snapshot, ctx.profile.featured)
    height = height_for(len(items))
    cards = [
        _card(ctx, item, PAD + (i % 2) * (CARD_W + 10), TOP + (i // 2) * (CARD_H + 10), i)
        for i, item in enumerate(items)
    ] or [
        text(
            FULL_W / 2,
            TOP + 50,
            "no public projects to feature yet",
            class_="md mut",
            text_anchor="middle",
        )
    ]
    return document(
        FULL_W,
        height,
        "Featured projects",
        stylesheet(t),
        panel(t, FULL_W, height, "Featured · public projects", "live from GitHub"),
        *cards,
    )


def _card(ctx: RenderContext, item: insights.Featured, x: float, y: float, index: int) -> Markup:
    t = ctx.theme
    repo = item.repo
    lang = repo.languages[0] if repo.languages else None
    desc = textwrap.wrap(repo.description or "No description provided.", DESC_CHARS)[:2]
    age = metrics.coarse_age(ctx.snapshot.fetched_at - repo.pushed_at)
    stats = [
        f"★ {repo.stars}",
        *([repo.release_tag] if repo.release_tag else []),
        f"{item.commits} commits",
        age,
    ]
    return group(
        rect(x, y, CARD_W, CARD_H, rx=10, fill=t.bg, stroke=t.border, fill_opacity=0.55),
        rect(x, y + 14, 3, 26, rx=1.5, fill=lang.color if lang else t.accent),
        text(
            x + 16,
            y + 26,
            truncate(repo.short_name, 40),
            class_="md",
            font_size=14,
            font_weight=700,
        ),
        text(
            x + CARD_W - 14,
            y + 26,
            truncate(repo.name_with_owner.split("/")[0], 22),
            class_="sm mut",
            text_anchor="end",
        ),
        *(text(x + 16, y + 48 + i * 15, line, class_="sm mut") for i, line in enumerate(desc)),
        circle(x + 20, y + CARD_H - 18, 4.5, fill=lang.color if lang else t.muted),
        text(x + 30, y + CARD_H - 14, truncate(lang.name if lang else "—", 12), class_="sm"),
        text(
            x + CARD_W - 14, y + CARD_H - 14, " · ".join(stats), class_="sm mut", text_anchor="end"
        ),
        class_="rise",
        style=f"animation-delay:{0.15 + index * 0.12:.2f}s",
    )
