"""Certifications rendered as `kubectl get certificates` (shown only when configured)."""

from __future__ import annotations

from pulse.render.context import RenderContext
from pulse.render.svg import Markup, document, group, rect, text, truncate
from pulse.render.theme import FULL_W, PAD, panel, stylesheet

TOP = 98
ROW_H = 20
COLS = (("NAME", PAD), ("ISSUER", 380), ("READY", 590), ("ISSUED", 670), ("EXPIRES", FULL_W - PAD))


def height_for(rows: int) -> int:
    return TOP + max(rows, 1) * ROW_H + 30


def render(ctx: RenderContext) -> Markup:
    t = ctx.theme
    certs = ctx.profile.certifications
    height = height_for(len(certs))
    year = ctx.snapshot.fetched_at.year
    rows = []
    for i, cert in enumerate(certs):
        y = TOP + i * ROW_H
        ready = cert.expires is None or cert.expires >= year
        rows.append(
            group(
                text(COLS[0][1], y, truncate(cert.name, 48), class_="md"),
                text(COLS[1][1], y, truncate(cert.issuer, 28), class_="md mut"),
                text(
                    COLS[2][1],
                    y,
                    "True" if ready else "False",
                    class_="md",
                    fill=t.ok if ready else t.crit,
                ),
                text(COLS[3][1], y, cert.issued, class_="md mut"),
                text(COLS[4][1], y, cert.expires or "never", class_="md mut", text_anchor="end"),
                class_="rise",
                style=f"animation-delay:{0.3 + i * 0.12:.2f}s",
            )
        )
    cursor_y = TOP + max(len(certs), 1) * ROW_H + 6
    return document(
        FULL_W,
        height,
        "Certifications",
        stylesheet(t),
        panel(t, FULL_W, height, "Certificates · cert-manager", f"{len(certs)} issued"),
        text(PAD, 58, "$", class_="md acc"),
        text(PAD + 14, 58, "kubectl get certificates -A", class_="md"),
        group(
            *(
                text(
                    x,
                    80,
                    name,
                    class_="sm mut",
                    letter_spacing="0.06em",
                    text_anchor="end" if name == "EXPIRES" else None,
                )
                for name, x in COLS
            )
        ),
        *rows,
        text(PAD, cursor_y, "$", class_="md acc"),
        rect(PAD + 14, cursor_y - 10, 7, 13, fill=t.accent, class_="blink"),
    )
