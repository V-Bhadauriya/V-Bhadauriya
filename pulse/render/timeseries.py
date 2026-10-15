"""Grafana-style weekly activity time series with p95 band and peak annotation."""

from __future__ import annotations

from pulse import metrics
from pulse.render.context import RenderContext
from pulse.render.svg import Markup, circle, document, el, group, line, path, text
from pulse.render.theme import HALF_H, HALF_W, PAD, panel, stylesheet

LEFT, RIGHT, TOP, BOTTOM = 40, HALF_W - PAD, 56, HALF_H - 34


def smooth_path(points: list[tuple[float, float]]) -> str:
    """Catmull-Rom spline through the points, expressed as cubic Béziers."""
    if not points:
        return ""
    if len(points) == 1:
        x, y = points[0]
        return f"M{x:.1f},{y:.1f}"
    parts = [f"M{points[0][0]:.1f},{points[0][1]:.1f}"]
    for i in range(len(points) - 1):
        p0 = points[max(i - 1, 0)]
        p1, p2 = points[i], points[i + 1]
        p3 = points[min(i + 2, len(points) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        c1y = min(c1[1], BOTTOM)
        c2y = min(c2[1], BOTTOM)
        parts.append(f"C{c1[0]:.1f},{c1y:.1f} {c2[0]:.1f},{c2y:.1f} {p2[0]:.1f},{p2[1]:.1f}")
    return " ".join(parts)


def render(ctx: RenderContext) -> Markup:
    t = ctx.theme
    weeks = metrics.weekly_series(ctx.snapshot)
    counts = [w.count for w in weeks]
    top_value = max(max(counts, default=0), 1)
    scale_max = _nice_ceiling(top_value)
    step = (RIGHT - LEFT) / max(len(weeks) - 1, 1)

    def y(value: float) -> float:
        return BOTTOM - (BOTTOM - TOP) * value / scale_max

    points = [(LEFT + i * step, y(c)) for i, c in enumerate(counts)]
    curve = smooth_path(points)
    area = f"{curve} L{RIGHT:.1f},{BOTTOM} L{LEFT},{BOTTOM} Z" if points else ""
    p95 = metrics.percentile(counts, 0.95)
    mean = sum(counts) / len(counts) if counts else 0.0

    return document(
        HALF_W,
        HALF_H,
        "Weekly activity time series",
        stylesheet(t),
        el(
            "defs",
            None,
            el(
                "linearGradient",
                {"id": "area", "x1": "0", "x2": "0", "y1": "0", "y2": "1"},
                el("stop", {"offset": "0", "stop-color": t.accent, "stop-opacity": "0.38"}),
                el("stop", {"offset": "1", "stop-color": t.accent, "stop-opacity": "0"}),
            ),
        ),
        panel(t, HALF_W, HALF_H, "Throughput · events/week", f"52w · Σ {sum(counts):,}"),
        _grid(scale_max, y),
        _month_labels(weeks, step),
        path(area, fill="url(#area)", class_="fade", style="animation-delay:1.2s")
        if area
        else None,
        path(curve, fill="none", stroke=t.accent, stroke_width=2, pathLength=1, class_="draw"),
        _threshold(ctx, y(p95), f"p95 {p95:.0f}", t.warn),
        _threshold(ctx, y(mean), f"avg {mean:.0f}", t.muted),
        _peak(ctx, weeks, points),
        _cursor(ctx, points),
    )


def _nice_ceiling(value: float) -> float:
    for base in (5, 10, 20, 25, 50, 100, 200, 250, 500, 1000):
        if value <= base:
            return float(base)
    return float(value)


def _grid(scale_max: float, y) -> Markup:
    rows = []
    for frac in (0, 0.25, 0.5, 0.75, 1):
        value = scale_max * frac
        rows.append(line(LEFT, y(value), RIGHT, y(value), class_="s-grid", stroke_width=1))
        rows.append(
            text(LEFT - 6, y(value) + 3, f"{value:.0f}", class_="sm mut", text_anchor="end")
        )
    return group(*rows)


def _month_labels(weeks, step: float) -> Markup:
    labels, last_month = [], None
    for i, week in enumerate(weeks):
        if week.start.month != last_month and week.start.month % 3 == 1:
            labels.append(text(LEFT + i * step, BOTTOM + 16, f"{week.start:%b}", class_="sm mut"))
        last_month = week.start.month
    return group(*labels)


def _threshold(ctx: RenderContext, y_pos: float, label: str, color: str) -> Markup:
    return group(
        line(LEFT, y_pos, RIGHT, y_pos, stroke=color, stroke_width=1, stroke_dasharray="3 4"),
        text(LEFT + 4, y_pos - 4, label, class_="sm", fill=color),
        class_="fade",
        style="animation-delay:1.6s",
    )


def _peak(ctx: RenderContext, weeks, points) -> Markup | None:
    if not weeks or max(w.count for w in weeks) == 0:
        return None
    index = max(range(len(weeks)), key=lambda i: weeks[i].count)
    x, y_pos = points[index]
    label = f"peak {weeks[index].count} · {weeks[index].start:%b %d}"
    anchor = "end" if x > (LEFT + RIGHT) / 2 else "start"
    offset = -8 if anchor == "end" else 8
    return group(
        line(x, y_pos, x, BOTTOM, stroke=ctx.theme.accent2, stroke_dasharray="2 3"),
        circle(x, y_pos, 3.5, fill=ctx.theme.accent2),
        text(x + offset, max(y_pos + 4, TOP + 10), label, class_="sm acc2", text_anchor=anchor),
        class_="fade",
        style="animation-delay:2.2s",
    )


def _cursor(ctx: RenderContext, points) -> Markup | None:
    if not points:
        return None
    x, y_pos = points[-1]
    return group(
        circle(x, y_pos, 4, fill=ctx.theme.accent, class_="ping"),
        circle(x, y_pos, 3.5, fill=ctx.theme.accent),
    )
