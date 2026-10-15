"""`kubectl logs -f` terminal streaming your latest commits, PRs and merges."""

from __future__ import annotations

from pulse import insights
from pulse.render.context import RenderContext
from pulse.render.svg import Markup, document, group, rect, text, truncate
from pulse.render.theme import FULL_W, PAD, panel, stylesheet

LINES = 10
LINE_H = 20
TOP = 82
HEIGHT = TOP + LINES * LINE_H + 34
TIME_X, LEVEL_X, SERVICE_X, MESSAGE_X = PAD, 132, 206, 470
SERVICE_CHARS, MESSAGE_CHARS = 34, 51


def render(ctx: RenderContext) -> Markup:
    t = ctx.theme
    lines = insights.deploy_log(ctx.snapshot, limit=LINES)
    namespace = ctx.profile.handle.split(".")[0]
    rows = [_line(ctx, line, i) for i, line in enumerate(lines)] or [
        text(PAD, TOP, "no events yet — waiting for the first deploy", class_="md mut")
    ]
    cursor_y = TOP + max(len(lines), 1) * LINE_H + 4
    return document(
        FULL_W,
        HEIGHT,
        "Live deploy log of recent commits and pull requests",
        stylesheet(t),
        panel(t, FULL_W, HEIGHT, "Deploy log · live", f"tail -n {LINES} · {ctx.profile.timezone}"),
        text(PAD, 58, "$", class_="md acc"),
        text(PAD + 14, 58, f"kubectl logs -f deploy/{namespace} --since=365d", class_="md"),
        *rows,
        text(PAD, cursor_y, "$", class_="md acc"),
        rect(PAD + 14, cursor_y - 10, 7, 13, fill=t.accent, class_="blink"),
    )


def _line(ctx: RenderContext, line: insights.LogLine, index: int) -> Markup:
    t = ctx.theme
    y = TOP + index * LINE_H
    color = {"MERGE": t.ok, "PR": t.warn}.get(line.level, t.accent2)
    local = line.at.astimezone(ctx.profile.tz)
    # Newest line first, but reveal oldest-to-newest like a streaming log.
    wait = 0.3 + (LINES - index) * 0.12
    return group(
        text(TIME_X, y, f"{local:%m-%d %H:%M}", class_="md mut"),
        text(LEVEL_X, y, f"[{line.level}]", class_="md", fill=color, font_weight=700),
        text(SERVICE_X, y, truncate(line.service, SERVICE_CHARS), class_="md acc"),
        text(MESSAGE_X, y, truncate(line.message, MESSAGE_CHARS), class_="md"),
        class_="fade",
        style=f"animation-delay:{wait:.2f}s",
    )
