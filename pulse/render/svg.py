"""Minimal, escaping-by-default SVG element builder."""

from __future__ import annotations

from html import escape


class Markup(str):
    """Already-rendered SVG; never escaped again."""


def _fmt(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def el(tag: str, attrs: dict[str, object] | None = None, *children: object) -> Markup:
    attr_text = "".join(
        f' {key.rstrip("_").replace("_", "-")}="{escape(_fmt(value), quote=True)}"'
        for key, value in (attrs or {}).items()
        if value is not None
    )
    body = "".join(
        child if isinstance(child, Markup) else escape(_fmt(child), quote=False)
        for child in children
        if child is not None
    )
    if not body:
        return Markup(f"<{tag}{attr_text}/>")
    return Markup(f"<{tag}{attr_text}>{body}</{tag}>")


def group(*children: object, **attrs: object) -> Markup:
    return el("g", attrs, *children)


def text(x: float, y: float, content: object, **attrs: object) -> Markup:
    return el("text", {"x": x, "y": y, **attrs}, content)


def rect(x: float, y: float, w: float, h: float, **attrs: object) -> Markup:
    return el("rect", {"x": x, "y": y, "width": w, "height": h, **attrs})


def line(x1: float, y1: float, x2: float, y2: float, **attrs: object) -> Markup:
    return el("line", {"x1": x1, "y1": y1, "x2": x2, "y2": y2, **attrs})


def circle(cx: float, cy: float, r: float, **attrs: object) -> Markup:
    return el("circle", {"cx": cx, "cy": cy, "r": r, **attrs})


def path(d: str, **attrs: object) -> Markup:
    return el("path", {"d": d, **attrs})


def concat(*parts: object) -> Markup:
    return Markup("".join(p if isinstance(p, Markup) else escape(str(p)) for p in parts if p))


def document(width: int, height: int, title: str, style: str, *body: object) -> Markup:
    return el(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "width": width,
            "height": height,
            "viewBox": f"0 0 {width} {height}",
            "role": "img",
            "aria-label": title,
        },
        el("title", None, title),
        el("style", None, Markup(style)),
        *body,
    )


def truncate(value: str, max_chars: int) -> str:
    return value if len(value) <= max_chars else value[: max_chars - 1] + "…"
