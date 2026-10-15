"""Service map: repos as nodes around you, linked by shared working days, with live packets."""

from __future__ import annotations

import math

from pulse import insights
from pulse.render.context import RenderContext
from pulse.render.svg import Markup, circle, document, el, group, path, text, truncate
from pulse.render.theme import FULL_W, panel, stylesheet

HEIGHT = 400
CX, CY = FULL_W / 2, 214
RX, RY = 320, 120
HUB_R = 30
MIN_R, MAX_R = 9, 24


def node_positions(count: int) -> list[tuple[float, float]]:
    """Evenly spaced on an ellipse around the hub, starting at the top."""
    return [
        (
            CX + RX * math.cos(-math.pi / 2 + 2 * math.pi * i / count),
            CY + RY * math.sin(-math.pi / 2 + 2 * math.pi * i / count),
        )
        for i in range(count)
    ]


def node_radius(events: int, peak: int) -> float:
    if peak <= 0:
        return MIN_R
    return MIN_R + (MAX_R - MIN_R) * math.sqrt(events / peak)


def render(ctx: RenderContext) -> Markup:
    t = ctx.theme
    smap = insights.service_map(ctx.snapshot)
    positions = dict(
        zip((n.repo for n in smap.nodes), node_positions(len(smap.nodes)), strict=True)
    )
    peak = max((n.events for n in smap.nodes), default=0)
    body = [_mesh(ctx, smap, positions)] if smap.nodes else []
    body += [_spoke(ctx, n, positions[n.repo], peak, i) for i, n in enumerate(smap.nodes)]
    body += [_node(ctx, n, positions[n.repo], peak, i) for i, n in enumerate(smap.nodes)]
    if not smap.nodes:
        body.append(
            text(
                CX,
                CY + 60,
                "no services active in the last 90 days",
                class_="md mut",
                text_anchor="middle",
            )
        )
    return document(
        FULL_W,
        HEIGHT,
        "Service map of active repositories",
        stylesheet(t),
        panel(
            t,
            FULL_W,
            HEIGHT,
            "Service map · last 90d",
            f"{len(smap.nodes)} services · {len(smap.edges)} shared-day links",
        ),
        *body,
        _hub(ctx),
    )


def _hub(ctx: RenderContext) -> Markup:
    t = ctx.theme
    name = ctx.profile.handle.split(".")[0]
    return group(
        circle(CX, CY, HUB_R + 6, fill=t.accent, fill_opacity=0.12, class_="glow"),
        circle(CX, CY, HUB_R, fill=t.bg, stroke=t.accent, stroke_width=2),
        text(CX, CY - 2, name, class_="md acc", text_anchor="middle", font_weight=700),
        text(CX, CY + 12, "gateway", class_="mut", font_size=8.5, text_anchor="middle"),
    )


def _mesh(ctx: RenderContext, smap: insights.ServiceMap, positions) -> Markup:
    """Faint curved links between services you worked on on the same days."""
    t = ctx.theme
    strongest = max((e.shared_days for e in smap.edges), default=1)
    links = []
    for edge in smap.edges:
        (x1, y1), (x2, y2) = positions[edge.a], positions[edge.b]
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        qx, qy = mx + (CX - mx) * 0.45, my + (CY - my) * 0.45
        links.append(
            path(
                f"M{x1:.1f},{y1:.1f} Q{qx:.1f},{qy:.1f} {x2:.1f},{y2:.1f}",
                fill="none",
                stroke=t.accent2,
                stroke_width=0.8 + 2.2 * edge.shared_days / strongest,
                stroke_opacity=0.35,
                stroke_dasharray="4 4",
            )
        )
    return group(*links, class_="fade", style="animation-delay:.8s")


def _spoke(ctx: RenderContext, node: insights.Node, pos, peak: int, index: int) -> Markup:
    t = ctx.theme
    x, y = pos
    d = f"M{CX:.1f},{CY:.1f} L{x:.1f},{y:.1f}"
    load = node.events / peak if peak else 0
    color = t.accent2 if node.is_private else t.accent
    packet_dur = 3.6 - 2.4 * load  # busier services move traffic faster
    return group(
        path(
            d,
            stroke=color,
            stroke_width=1 + 3 * load,
            stroke_opacity=0.45,
            fill="none",
            pathLength=1,
            class_="draw",
            style=f"animation-delay:{0.2 + index * 0.1:.2f}s",
        ),
        el(
            "circle",
            {"r": 2.6, "fill": color},
            el(
                "animateMotion",
                {
                    "dur": f"{packet_dur:.1f}s",
                    "begin": f"{index * 0.37:.2f}s",
                    "repeatCount": "indefinite",
                    "path": d,
                },
            ),
        ),
    )


def _node(ctx: RenderContext, node: insights.Node, pos, peak: int, index: int) -> Markup:
    t = ctx.theme
    x, y = pos
    r = node_radius(node.events, peak)
    color = t.accent2 if node.is_private else t.accent
    below = y >= CY
    label_y = y + r + 14 if below else y - r - 18
    return group(
        circle(x, y, r, fill=color, fill_opacity=0.18, stroke=color, stroke_width=1.6),
        circle(x, y, 3, fill=color),
        text(
            x,
            label_y,
            truncate(node.label, 30),
            class_="sm",
            text_anchor="middle",
            fill=t.muted if node.is_private else t.text,
        ),
        text(
            x,
            label_y + 11,
            f"{node.events:,} events",
            class_="mut",
            font_size=8.5,
            text_anchor="middle",
        ),
        class_="rise",
        style=f"animation-delay:{0.4 + index * 0.1:.2f}s",
    )
