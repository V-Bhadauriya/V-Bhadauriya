"""Static constants and validated loading of profile.yml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

GRAPHQL_URL = "https://api.github.com/graphql"
USER_AGENT = "pulse-profile-generator/0.1"
HTTP_TIMEOUT_S = 30.0
MAX_RETRIES = 3
RETRY_BACKOFF_S = 2.0
MAX_RATE_LIMIT_WAIT_S = 120.0
MAX_PAGES = 50
# Publish anyway if GitHub refused at most this share of items (e.g. a teammate's private repo).
MAX_DENIED_RATIO = 0.05

LOOKBACK_DAYS = 365
TRACE_WINDOW_DAYS = 14
MAX_COMMITS_PER_REPO = 2000
MAX_PULL_REQUESTS = 1000
REPO_BATCH_SIZE = 8
# Commit history with line stats is expensive server-side; small batches avoid 502 timeouts.
HISTORY_BATCH_SIZE = 2
HISTORY_PAGE_SIZE = 50

PRIVATE_LABEL = "private repo"
MAX_SVG_BYTES = 100_000

ASSET_NAMES = ("status", "activity", "slo", "timeseries", "heatmap", "trace", "resources", "pods")


class ConfigError(ValueError):
    """Raised when profile.yml is missing or invalid."""


@dataclass(frozen=True)
class Product:
    name: str
    url: str
    summary: str


@dataclass(frozen=True)
class Work:
    title: str
    company: str
    company_url: str
    products: tuple[Product, ...] = ()


@dataclass(frozen=True)
class Profile:
    login: str
    handle: str
    display_name: str
    tagline: str
    role: str
    region: str
    timezone: str
    focus: tuple[str, ...]
    stack: tuple[str, ...]
    links: tuple[tuple[str, str], ...]
    kind: str = "Engineer"
    work: Work | None = None

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


_REQUIRED_STR = ("login", "handle", "display_name", "tagline", "role", "region", "timezone")


def load_profile(path: Path) -> Profile:
    if not path.is_file():
        raise ConfigError(f"profile file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"profile file is not valid YAML: {exc}") from exc
    return parse_profile(raw)


def parse_profile(raw: object) -> Profile:
    if not isinstance(raw, dict):
        raise ConfigError("profile must be a mapping")
    for key in _REQUIRED_STR:
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"profile.{key} must be a non-empty string")
        _check_inline(key, value)
    try:
        ZoneInfo(raw["timezone"])
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfigError(f"profile.timezone is not a valid IANA zone: {raw['timezone']}") from exc

    links = raw.get("links") or {}
    if not isinstance(links, dict) or not all(
        isinstance(k, str) and isinstance(v, str) and v.startswith("https://")
        for k, v in links.items()
    ):
        raise ConfigError("profile.links must map names to https:// URLs")

    return Profile(
        login=raw["login"].strip(),
        handle=raw["handle"].strip(),
        display_name=raw["display_name"].strip(),
        tagline=raw["tagline"].strip(),
        role=raw["role"].strip(),
        region=raw["region"].strip(),
        timezone=raw["timezone"].strip(),
        focus=_str_list(raw, "focus"),
        stack=_str_list(raw, "stack"),
        links=tuple(links.items()),
        kind=_kind(raw.get("kind", "Engineer")),
        work=_work(raw.get("work")),
    )


def _kind(value: object) -> str:
    if not isinstance(value, str) or not value.isalnum():
        raise ConfigError("profile.kind must be a single alphanumeric word, e.g. DataScientist")
    return value


def _https(key: str, value: object) -> str:
    if not isinstance(value, str) or not value.startswith("https://"):
        raise ConfigError(f"profile.{key} must be an https:// URL")
    _check_inline(key, value)
    return value


def _text(key: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"profile.{key} must be a non-empty string")
    _check_inline(key, value)
    return value.strip()


def _work(raw: object) -> Work | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ConfigError("profile.work must be a mapping")
    products = raw.get("products") or []
    if not isinstance(products, list) or not all(isinstance(p, dict) for p in products):
        raise ConfigError("profile.work.products must be a list of mappings")
    return Work(
        title=_text("work.title", raw.get("title")),
        company=_text("work.company", raw.get("company")),
        company_url=_https("work.company_url", raw.get("company_url")),
        products=tuple(
            Product(
                name=_text("work.products.name", p.get("name")),
                url=_https("work.products.url", p.get("url")),
                summary=_text("work.products.summary", p.get("summary")),
            )
            for p in products
        ),
    )


def _str_list(raw: dict, key: str) -> tuple[str, ...]:
    value = raw.get(key) or []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"profile.{key} must be a list of strings")
    for item in value:
        _check_inline(key, item)
    return tuple(v.strip() for v in value if v.strip())


def _check_inline(key: str, value: str) -> None:
    """Values land inside a README code fence; backticks or newlines could break out of it."""
    if "`" in value or "\n" in value or "\r" in value:
        raise ConfigError(f"profile.{key} must not contain backticks or line breaks")
