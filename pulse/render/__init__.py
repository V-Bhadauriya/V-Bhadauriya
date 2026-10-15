"""Panel registry: asset name -> renderer."""

from __future__ import annotations

from collections.abc import Callable

from pulse.render import heatmap, pods, resources, slo, status, timeseries, trace
from pulse.render.context import RenderContext
from pulse.render.svg import Markup

Renderer = Callable[[RenderContext], Markup]

PANELS: dict[str, Renderer] = {
    "status": status.render,
    "slo": slo.render,
    "timeseries": timeseries.render,
    "heatmap": heatmap.render,
    "trace": trace.render,
    "resources": resources.render,
    "pods": pods.render,
}
