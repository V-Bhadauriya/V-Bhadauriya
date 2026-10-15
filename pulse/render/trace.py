"""Distributed-trace waterfall: one span per repo over the trace window."""

from __future__ import annotations

from datetime import datetime, timedelta

from pulse import config, metrics
from pulse.render.context import RenderContext
from pulse.render.svg import Markup, circle, document, group, line, path, rect, text, truncate
from pulse.render.theme import HALF_H, HALF_W, PAD, panel, stylesheet

NAME_X, COUNT_X = PAD, 146
TL_LEFT, TL_RIGHT = 158, HALF_W - PAD - 6
ROW_Y0, ROW_H = 72, 22
MAX_ROWS = 6
MIN_SPAN_W = 4


def render(ctx: RenderContext) -> Markup:
    t = ctx.theme
    now = ctx.snapshot.fetched_at
    start = now - timedelta(days=config.TRACE_WINDOW_DAYS)
    spans = metrics.trace_spans(ctx.snapshot, max_spans=MAX_ROWS)
    body = (
        [_row(ctx, span, i, start, now) for i, span in enumerate(spans)]
        if spans
        else [
            text(
                HALF_W / 2,
                130,
                "no spans in window — service idle",
                class_="md mut",
                text_anchor="middle",
            )
        ]
    )
    events = sum(len(s.events) for s in spans)
    return document(
        HALF_W,
        HALF_H,
        "Trace waterfall of recent activity",
        stylesheet(t),
        panel(t, HALF_W, HALF_H, "Trace · last 14d", f"{len(spans)} spans · {events} events"),
        _axis(ctx, start, now),
        *body,
        _legend(ctx),
    )


def x_for(at: datetime, start: datetime, end: datetime) -> float:
    total = (end - start).total_seconds() or 1.0
    frac = min(max((at - start).total_seconds() / total, 0.0), 1.0)
    return TL_LEFT + (TL_RIGHT - TL_LEFT) * frac


def _axis(ctx: RenderContext, start: datetime, now: datetime) -> Markup:
    marks = []
    for days_ago in (14, 7, 0):
        x = x_for(now - timedelta(days=days_ago), start, now)
        label = "now" if days_ago == 0 else f"-{days_ago}d"
        anchor = "end" if days_ago == 0 else "middle" if days_ago == 7 else "start"
        marks.append(text(x, 54, label, class_="sm mut", text_anchor=anchor))
        marks.append(
            line(x, 60, x, ROW_Y0 + MAX_ROWS * ROW_H - 8, class_="s-grid", stroke_dasharray="2 3")
        )
    marks.append(text(NAME_X, 54, "SERVICE", class_="sm mut", letter_spacing="0.1em"))
    marks.append(text(COUNT_X, 54, "EV", class_="sm mut", text_anchor="end"))
    return group(*marks)


def _row(ctx: RenderContext, span: metrics.Span, index: int, start: datetime, now: datetime):
    t = ctx.theme
    y = ROW_Y0 + index * ROW_H
    x1 = x_for(span.start, start, now)
    x2 = max(x_for(span.end, start, now), x1 + MIN_SPAN_W)
    color = t.accent2 if span.is_private else t.accent
    name = truncate(span.service, 15)
    wait = 0.3 + index * 0.18
    return group(
        text(NAME_X, y + 4, name, class_="md", fill=t.muted if span.is_private else t.text),
        text(COUNT_X, y + 4, len(span.events), class_="sm mut", text_anchor="end"),
        rect(
            x1,
            y - 6,
            x2 - x1,
            12,
            rx=3,
            fill=color,
            fill_opacity=0.22,
            stroke=color,
            stroke_opacity=0.7,
            class_="growx",
            style=f"animation-delay:{wait:.2f}s",
        ),
        group(
            *(_event_mark(ctx, e, x_for(e.at, start, now), y) for e in span.events),
            class_="fade",
            style=f"animation-delay:{wait + 0.6:.2f}s",
        ),
    )


def _event_mark(ctx: RenderContext, event: metrics.Event, x: float, y: float) -> Markup:
    t = ctx.theme
    if event.kind == "commit":
        return line(x, y - 5, x, y + 5, stroke=t.text, stroke_width=1.2, opacity=0.8)
    if event.kind == "pr":
        return circle(x, y, 2.2, fill=t.warn)
    return path(f"M{x:.1f},{y - 3.5:.1f} l3.5,3.5 l-3.5,3.5 l-3.5,-3.5 Z", fill=t.ok)


def _legend(ctx: RenderContext) -> Markup:
    t = ctx.theme
    y = HALF_H - 16
    return group(
        line(PAD + 2, y - 8, PAD + 2, y + 2, stroke=t.text, stroke_width=1.2),
        text(PAD + 9, y, "commit", class_="sm mut"),
        circle(PAD + 70, y - 3, 2.6, fill=t.warn),
        text(PAD + 77, y, "PR opened", class_="sm mut"),
        path(f"M{PAD + 150},{y - 7} l4,4 l-4,4 l-4,-4 Z", fill=t.ok),
        text(PAD + 158, y, "merged", class_="sm mut"),
        rect(PAD + 216, y - 8, 14, 9, rx=2, fill=t.accent2, fill_opacity=0.3, stroke=t.accent2),
        text(PAD + 235, y, "private (anonymised)", class_="sm mut"),
    )
