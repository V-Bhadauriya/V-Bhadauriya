"""Alertmanager-style view of pull requests that have been open too long."""

from __future__ import annotations

from pulse import insights
from pulse.render.context import RenderContext
from pulse.render.svg import Markup, circle, document, group, rect, text, truncate
from pulse.render.theme import FULL_W, PAD, panel, stylesheet

MAX_ROWS = 5
ROW_H = 26
TOP = 86


def height_for(rows: int) -> int:
    return TOP + max(rows, 1) * ROW_H + 26


def render(ctx: RenderContext) -> Markup:
    t = ctx.theme
    alerts = insights.stale_prs(ctx.snapshot)
    shown = alerts[:MAX_ROWS]
    height = height_for(len(shown))
    critical = sum(1 for a in alerts if a.severity == "critical")
    subtitle = f"{len(alerts)} firing · {critical} critical" if alerts else "0 firing"
    body = [_row(ctx, a, i) for i, a in enumerate(shown)] or [_all_clear(ctx)]
    if len(alerts) > MAX_ROWS:
        body.append(
            text(PAD, height - 12, f"+{len(alerts) - MAX_ROWS} more firing", class_="sm mut")
        )
    return document(
        FULL_W,
        height,
        "Alerts for long-open pull requests",
        stylesheet(t),
        panel(t, FULL_W, height, "Alerts · PullRequestStale", subtitle),
        text(PAD, 58, "SEVERITY", class_="sm mut", letter_spacing="0.1em"),
        text(130, 58, "SERVICE", class_="sm mut", letter_spacing="0.1em"),
        text(410, 58, "SUMMARY", class_="sm mut", letter_spacing="0.1em"),
        text(FULL_W - PAD, 58, "FOR", class_="sm mut", letter_spacing="0.1em", text_anchor="end"),
        *body,
    )


def _row(ctx: RenderContext, alert: insights.Alert, index: int) -> Markup:
    t = ctx.theme
    y = TOP + index * ROW_H
    color = t.crit if alert.severity == "critical" else t.warn
    return group(
        circle(PAD + 5, y - 4, 4, fill=color, class_="ping"),
        circle(PAD + 5, y - 4, 4, fill=color),
        rect(
            PAD + 14,
            y - 14,
            84,
            18,
            rx=9,
            fill=color,
            fill_opacity=0.15,
            stroke=color,
            stroke_opacity=0.6,
        ),
        text(
            PAD + 56,
            y,
            alert.severity.upper(),
            class_="sm",
            fill=color,
            font_weight=700,
            text_anchor="middle",
        ),
        text(130, y, truncate(alert.service, 36), class_="md acc"),
        text(410, y, truncate(alert.title, 50), class_="md"),
        text(FULL_W - PAD, y, f"{alert.age_days}d", class_="md mut", text_anchor="end"),
        class_="rise",
        style=f"animation-delay:{0.2 + index * 0.1:.2f}s",
    )


def _all_clear(ctx: RenderContext) -> Markup:
    t = ctx.theme
    return group(
        circle(PAD + 5, TOP - 4, 5, fill=t.ok),
        text(
            PAD + 18,
            TOP,
            f"All clear — no pull requests open longer than {insights.STALE_PR_DAYS} days.",
            class_="md ok",
        ),
    )
