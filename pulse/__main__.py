"""CLI: fetch telemetry, render panels, rewrite README sections."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

from pulse import config, readme
from pulse.config import ConfigError, Profile, load_profile
from pulse.github_client import FetchResult, GitHubClient, GitHubError, fetch_snapshot
from pulse.models import Snapshot
from pulse.render import PANELS
from pulse.render.context import RenderContext
from pulse.render.theme import THEMES

log = logging.getLogger("pulse")


class RenderError(RuntimeError):
    """Raised when a rendered asset fails validation."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="pulse", description=__doc__)
    parser.add_argument("--profile", type=Path, default=Path("profile.yml"))
    parser.add_argument("--out", type=Path, default=Path("assets"))
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    parser.add_argument("--fixture", type=Path, help="render from a saved snapshot, no API calls")
    parser.add_argument("--save-snapshot", type=Path, help="write the fetched snapshot as JSON")
    return parser.parse_args(argv)


def load_snapshot(args: argparse.Namespace, profile: Profile) -> FetchResult:
    if args.fixture:
        data = json.loads(args.fixture.read_text(encoding="utf-8"))
        return FetchResult(Snapshot.from_dict(data), frozenset())
    token = os.environ.get("PULSE_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    client = GitHubClient(token)
    return fetch_snapshot(client, profile.login, datetime.now(UTC))


def render_assets(snapshot: Snapshot, profile: Profile) -> dict[str, str]:
    """Render every panel in every theme; validate before anything touches disk."""
    assets: dict[str, str] = {}
    for theme in THEMES:
        ctx = RenderContext(snapshot=snapshot, profile=profile, theme=theme)
        for name, renderer in PANELS.items():
            filename = f"{name}-{theme.name}.svg"
            svg = str(renderer(ctx))
            validate_svg(filename, svg)
            assets[filename] = svg
    return assets


def validate_svg(filename: str, svg: str) -> None:
    size = len(svg.encode("utf-8"))
    if size > config.MAX_SVG_BYTES:
        raise RenderError(f"{filename} is {size} bytes (limit {config.MAX_SVG_BYTES})")
    try:
        ElementTree.fromstring(svg)
    except ElementTree.ParseError as exc:
        raise RenderError(f"{filename} is not well-formed XML: {exc}") from exc


def check_for_leaks(outputs: dict[str, str], private_names: frozenset[str]) -> None:
    """Defence in depth: refuse to write anything that contains a real private repo name."""
    needles = [name.lower() for name in private_names]
    for filename, content in outputs.items():
        haystack = content.lower()
        if any(needle in haystack for needle in needles):
            # Deliberately do not print the matched name: CI logs are public.
            raise RenderError(f"{filename} contains a private repository name; refusing to write")


def write_outputs(args: argparse.Namespace, profile: Profile, fetched: FetchResult) -> None:
    snapshot = fetched.snapshot
    assets = render_assets(snapshot, profile)
    current = args.readme.read_text(encoding="utf-8")
    updated = readme.replace_sections(
        current,
        {
            "manifest": readme.manifest(profile, snapshot),
            "links": readme.links(profile),
            "footer": readme.footer(snapshot),
        },
    )
    check_for_leaks({**assets, args.readme.name: updated}, fetched.private_names)
    args.out.mkdir(parents=True, exist_ok=True)
    for filename, svg in assets.items():
        (args.out / filename).write_text(svg, encoding="utf-8")
    if updated != current:
        args.readme.write_text(updated, encoding="utf-8")
    log.info("wrote %d assets to %s", len(assets), args.out)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args(argv)
    try:
        profile = load_profile(args.profile)
        fetched = load_snapshot(args, profile)
        if args.save_snapshot:
            payload = json.dumps(fetched.snapshot.to_dict(), indent=1)
            args.save_snapshot.write_text(payload, "utf-8")
        write_outputs(args, profile, fetched)
    except (ConfigError, GitHubError, RenderError, readme.MarkerError, OSError) as exc:
        log.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
