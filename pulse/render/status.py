"""Header banner: service status, identity, KPIs and a live heartbeat trace."""

from __future__ import annotations

from pulse import metrics
from pulse.render.context import RenderContext
from pulse.render.svg import Markup, circle, document, el, group, path, rect, text, truncate
from pulse.render.theme import FULL_W, PAD, delay, stylesheet

HEIGHT = 206
CHAR_W_13 = 7.83  # advance width of a 13px monospace glyph
HEARTBEAT_DAYS = 90
ECG_TOP, ECG_BASE = 150, 172

EXTRA_CSS = """
@keyframes type{from{transform:scaleX(0)}}
.type{transform-box:fill-box;transform-origin:left center;animation:type 2.4s steps(48) .5s both;}
"""


def render(ctx: RenderContext) -> Markup:
    t, snap, prof = ctx.theme, ctx.snapshot, ctx.profile
    return document(
        FULL_W,
        HEIGHT,
        f"{prof.display_name} — live status",
        stylesheet(t, EXTRA_CSS),
        _defs(ctx),
        rect(0.5, 0.5, FULL_W - 1, HEIGHT - 1, rx=12, fill=t.panel, stroke=t.border),
        rect(1, 1, FULL_W - 2, HEIGHT - 2, rx=12, fill="url(#halo)"),
        _identity(ctx),
        _kpis(ctx),
        _heartbeat(ctx),
        text(PAD + 8, HEIGHT - 8, f"heartbeat · {HEARTBEAT_DAYS}d", class_="sm mut"),
        text(
            FULL_W - PAD - 8,
            HEIGHT - 8,
            f"scraped {snap.fetched_at:%Y-%m-%d} UTC",
            class_="sm mut",
            text_anchor="end",
        ),
    )


def _defs(ctx: RenderContext) -> Markup:
    t = ctx.theme
    halo = el(
        "radialGradient",
        {"id": "halo", "cx": "0.12", "cy": "0.1", "r": "0.9"},
        el("stop", {"offset": "0", "stop-color": t.accent, "stop-opacity": "0.14"}),
        el("stop", {"offset": "0.6", "stop-color": t.accent2, "stop-opacity": "0.04"}),
        el("stop", {"offset": "1", "stop-color": t.panel, "stop-opacity": "0"}),
    )
    fade = el(
        "linearGradient",
        {"id": "ecgfade", "x1": "0", "x2": "1"},
        el("stop", {"offset": "0", "stop-color": t.accent, "stop-opacity": "0"}),
        el("stop", {"offset": "0.25", "stop-color": t.accent, "stop-opacity": "0.9"}),
        el("stop", {"offset": "1", "stop-color": t.accent, "stop-opacity": "1"}),
    )
    return el("defs", None, halo, fade)


def _identity(ctx: RenderContext) -> Markup:
    t, prof = ctx.theme, ctx.profile
    x = PAD + 10
    tagline = f"> {truncate(prof.tagline, 50)}"
    caret_x = x + len(tagline) * CHAR_W_13 + 3
    return group(
        circle(x + 5, 31, 5, fill=t.ok, class_="ping"),
        circle(x + 5, 31, 5, fill=t.ok),
        text(x + 18, 35, "OPERATIONAL", class_="md ok", font_weight=700, letter_spacing="0.12em"),
        text(x + 122, 35, f"· {prof.region}", class_="md mut"),
        text(x, 78, prof.handle, class_="xl rise"),
        el(
            "g",
            {"class": "type"},
            text(x, 106, tagline, class_="md acc", font_size=13),
        ),
        rect(caret_x, 95, 7, 14, fill=t.accent, class_="blink"),
        text(x, 128, f"role={prof.role}  tz={prof.timezone}", class_="sm mut fade"),
    )


def _kpis(ctx: RenderContext) -> Markup:
    snap = ctx.snapshot
    current, longest = metrics.streaks(snap)
    deploy = metrics.last_deploy(snap)
    deploy_label = (
        f"{truncate(deploy[0], 14)} · {metrics.coarse_age(snap.fetched_at - deploy[1])}"
        if deploy
        else "—"
    )
    cells = (
        ("UPTIME", metrics.uptime(snap.created_at, snap.fetched_at).label(), "since signup"),
        ("EVENTS · 365D", f"{metrics.total_activity(snap):,}", "commits + PRs + contribs"),
        ("STREAK", f"{current}d", f"longest {longest}d"),
        ("LAST DEPLOY", deploy_label, "most recent push"),
    )
    x0, y0, w, h, gap = 452, 20, 192, 56, 8
    return group(
        *(
            _kpi(ctx, x0 + (i % 2) * (w + gap), y0 + (i // 2) * (h + gap), w, h, cell, i)
            for i, cell in enumerate(cells)
        )
    )


def _kpi(
    ctx: RenderContext, x: float, y: float, w: float, h: float, cell: tuple, index: int
) -> Markup:
    t = ctx.theme
    label, value, hint = cell
    size = 18 if len(value) < 12 else 13
    return group(
        rect(x, y, w, h, rx=8, fill=t.bg, stroke=t.border, fill_opacity=0.55),
        rect(x, y + 10, 2, h - 20, fill=t.accent2 if index % 2 else t.accent),
        text(x + 12, y + 17, label, class_="sm mut", letter_spacing="0.1em"),
        text(x + 12, y + 38, value, font_size=size, font_weight=700),
        text(x + 12, y + 50, hint, class_="mut", font_size=8.5),
        class_="rise",
        style=delay(0.25 + index * 0.12),
    )


def ecg_path(counts: list[int], x0: float, x1: float, top: float, base: float) -> str:
    """ECG-style polyline: a flat baseline with a QRS spike per active day."""
    if not counts:
        return f"M{x0:.1f},{base:.1f} L{x1:.1f},{base:.1f}"
    step = (x1 - x0) / len(counts)
    peak = max(max(counts), 1)
    amp_max = base - top
    parts = [f"M{x0:.1f},{base:.1f}"]
    for i, count in enumerate(counts):
        x = x0 + i * step
        if count:
            amp = amp_max * (0.25 + 0.75 * (count / peak) ** 0.6)
            parts += [
                f"L{x + step * 0.30:.1f},{base:.1f}",
                f"L{x + step * 0.42:.1f},{base + amp * 0.18:.1f}",
                f"L{x + step * 0.55:.1f},{base - amp:.1f}",
                f"L{x + step * 0.68:.1f},{base + amp * 0.32:.1f}",
                f"L{x + step * 0.80:.1f},{base:.1f}",
            ]
    parts.append(f"L{x1:.1f},{base:.1f}")
    return " ".join(parts)


def _heartbeat(ctx: RenderContext) -> Markup:
    t = ctx.theme
    counts = [c for _, c in metrics.daily_activity(ctx.snapshot)[-HEARTBEAT_DAYS:]]
    x0, x1 = PAD + 8, FULL_W - PAD - 8
    d = ecg_path(counts, x0, x1, ECG_TOP - 8, ECG_BASE)
    return group(
        el("line", {"x1": x0, "y1": ECG_BASE, "x2": x1, "y2": ECG_BASE, "class": "s-grid"}),
        path(
            d,
            fill="none",
            stroke="url(#ecgfade)",
            stroke_width=1.6,
            stroke_linejoin="round",
            pathLength=1,
            class_="draw",
        ),
        _tracer(t.accent, d),
    )


def _tracer(color: str, d: str) -> Markup:
    """A glowing dot that keeps sweeping along the heartbeat (SMIL, works in <img>)."""
    return el(
        "circle",
        {"r": 3.2, "fill": color},
        el("animateMotion", {"dur": "9s", "repeatCount": "indefinite", "path": d}),
    )
