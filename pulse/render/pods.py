"""Public repositories rendered as `kubectl get pods` output."""

from __future__ import annotations

from pulse import metrics
from pulse.render.context import RenderContext
from pulse.render.svg import Markup, document, group, rect, text, truncate
from pulse.render.theme import HALF_H, HALF_W, PAD, panel, stylesheet

COLS = (("NAME", PAD), ("READY", 206), ("STATUS", 248), ("RESTARTS", 322), ("AGE", HALF_W - PAD))
ROW_Y0, ROW_H = 98, 18
MAX_ROWS = 6


def format_age(days: int) -> str:
    if days >= 365:
        return f"{days // 365}y{(days % 365) // 30}m" if days % 365 >= 30 else f"{days // 365}y"
    return f"{days}d"


def render(ctx: RenderContext) -> Markup:
    t = ctx.theme
    pods = metrics.pods(ctx.snapshot, limit=MAX_ROWS)
    namespace = ctx.profile.handle.split(".")[0]
    command = f"kubectl get pods -n {namespace}"
    prompt_y = ROW_Y0 + max(len(pods), 1) * ROW_H + 8
    rows = [_row(ctx, p, i) for i, p in enumerate(pods)] or [
        text(PAD, ROW_Y0, f"No resources found in {namespace} namespace.", class_="md mut")
    ]
    return document(
        HALF_W,
        HALF_H,
        "Repositories as Kubernetes pods",
        stylesheet(t),
        panel(t, HALF_W, HALF_H, "Workloads", f"{len(pods)} public pods"),
        text(PAD, 58, "$", class_="md acc"),
        text(PAD + 14, 58, command, class_="md"),
        group(
            *(
                text(
                    x,
                    80,
                    name,
                    class_="sm mut",
                    letter_spacing="0.06em",
                    text_anchor="end" if name == "AGE" else None,
                )
                for name, x in COLS
            ),
            class_="fade",
            style="animation-delay:.3s",
        ),
        *rows,
        text(PAD, prompt_y, "$", class_="md acc"),
        rect(PAD + 14, prompt_y - 10, 7, 13, fill=t.accent, class_="blink"),
    )


def _row(ctx: RenderContext, pod: metrics.Pod, index: int) -> Markup:
    t = ctx.theme
    y = ROW_Y0 + index * ROW_H
    color = {"Running": t.ok, "Idle": t.warn}.get(pod.status, t.muted)
    ready = "1/1" if pod.status == "Running" else "0/1"
    return group(
        text(COLS[0][1], y, truncate(pod.name, 24), class_="md"),
        text(COLS[1][1], y, ready, class_="md mut"),
        text(COLS[2][1], y, pod.status, class_="md", fill=color),
        text(COLS[3][1], y, pod.restarts, class_="md mut"),
        text(COLS[4][1], y, format_age(pod.age_days), class_="md mut", text_anchor="end"),
        class_="rise",
        style=f"animation-delay:{0.5 + index * 0.14:.2f}s",
    )
