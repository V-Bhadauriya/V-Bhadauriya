"""Colour tokens, shared CSS (animations, reduced motion) and panel chrome."""

from __future__ import annotations

from dataclasses import dataclass

from pulse.render.svg import Markup, circle, el, group, rect, text

FULL_W = 860
HEADER_H = 34
PAD = 16
FONT = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace"


@dataclass(frozen=True)
class Theme:
    name: str
    bg: str
    panel: str
    border: str
    grid: str
    text: str
    muted: str
    accent: str
    accent2: str
    ok: str
    warn: str
    crit: str


DARK = Theme(
    name="dark",
    bg="#0a0e14",
    panel="#0f141b",
    border="#1e2732",
    grid="#18212b",
    text="#d6e2ee",
    muted="#6e7f91",
    accent="#38e1c6",
    accent2="#8b7cf6",
    ok="#3fd07f",
    warn="#f2b134",
    crit="#ff5d6c",
)

LIGHT = Theme(
    name="light",
    bg="#ffffff",
    panel="#f7f9fb",
    border="#d5dde6",
    grid="#e7edf3",
    text="#16202b",
    muted="#5d6b7a",
    accent="#0b8f80",
    accent2="#6a55e0",
    ok="#1a8f4f",
    warn="#b7790b",
    crit="#d42c3d",
)

THEMES = (DARK, LIGHT)


def stylesheet(theme: Theme, extra: str = "") -> str:
    t = theme
    return f"""
text{{font-family:{FONT};fill:{t.text};}}
.mut{{fill:{t.muted};}} .acc{{fill:{t.accent};}} .acc2{{fill:{t.accent2};}}
.ok{{fill:{t.ok};}} .warn{{fill:{t.warn};}} .crit{{fill:{t.crit};}}
.s-acc{{stroke:{t.accent};}} .s-grid{{stroke:{t.grid};}} .s-mut{{stroke:{t.muted};}}
.ttl{{font-size:11px;letter-spacing:.14em;font-weight:700;}}
.sm{{font-size:10px;}} .md{{font-size:12px;}} .lg{{font-size:20px;font-weight:700;}}
.xl{{font-size:28px;font-weight:800;letter-spacing:-.01em;}}
@keyframes fade{{from{{opacity:0}}}}
@keyframes rise{{from{{opacity:0;transform:translateY(6px)}}}}
@keyframes draw{{from{{stroke-dashoffset:1}}}}
@keyframes growx{{from{{transform:scaleX(0)}}}}
@keyframes growy{{from{{transform:scaleY(0)}}}}
@keyframes ping{{0%{{opacity:.7;transform:scale(1)}}100%{{opacity:0;transform:scale(3.2)}}}}
@keyframes blink{{50%{{opacity:0}}}}
@keyframes glow{{50%{{opacity:.35}}}}
.fade{{animation:fade .9s ease-out both;}}
.rise{{animation:rise .7s cubic-bezier(.2,.7,.2,1) both;}}
.draw{{stroke-dasharray:1;stroke-dashoffset:0;animation:draw 2.4s cubic-bezier(.6,.1,.2,1) both;}}
.growx{{transform-box:fill-box;transform-origin:left center;
  animation:growx .9s cubic-bezier(.2,.7,.2,1) both;}}
.growy{{transform-box:fill-box;transform-origin:center bottom;
  animation:growy .8s cubic-bezier(.2,.7,.2,1) both;}}
.ping{{transform-box:fill-box;transform-origin:center;animation:ping 2s ease-out infinite;}}
.blink{{animation:blink 1.1s steps(1) infinite;}}
.glow{{animation:glow 2.6s ease-in-out infinite;}}
{extra}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important;}}}}
"""


def delay(seconds: float) -> str:
    return f"animation-delay:{seconds:.2f}s"


def panel(theme: Theme, width: int, height: int, title: str, subtitle: str = "") -> Markup:
    """Background, dot grid and Grafana-like header bar shared by every panel."""
    t = theme
    pattern = el(
        "pattern",
        {"id": "dots", "width": 14, "height": 14, "patternUnits": "userSpaceOnUse"},
        circle(1, 1, 0.9, fill=t.grid),
    )
    return group(
        el("defs", None, pattern),
        rect(0.5, 0.5, width - 1, height - 1, rx=10, fill=t.panel, stroke=t.border),
        rect(1, HEADER_H, width - 2, height - HEADER_H - 1, fill="url(#dots)", opacity=0.9),
        el("line", {"x1": 1, "y1": HEADER_H, "x2": width - 1, "y2": HEADER_H, "stroke": t.border}),
        rect(PAD, 13, 8, 8, rx=2, fill=t.accent),
        text(PAD + 16, 21, title.upper(), class_="ttl"),
        text(width - PAD, 21, subtitle, class_="sm mut", text_anchor="end") if subtitle else None,
    )


def status_color(theme: Theme, ratio: float, *, invert: bool = False) -> str:
    """Green / amber / red for a 0..1 health ratio."""
    value = 1 - ratio if invert else ratio
    if value >= 0.66:
        return theme.ok
    if value >= 0.33:
        return theme.warn
    return theme.crit
