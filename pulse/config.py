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
SEARCH_RESULT_CAP = 1000  # GitHub search never returns more
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

ASSET_NAMES = (
    "status",
    "activity",
    "toolchain",
    "slo",
    "timeseries",
    "heatmap",
    "trace",
    "resources",
    "pods",
)


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
class StackGroup:
    label: str  # "" for an ungrouped (flat list) stack
    items: tuple[str, ...]

    @property
    def key(self) -> str:
        """camelCase identifier for the YAML manifest, e.g. "ML frameworks" -> mlFrameworks."""
        words = "".join(c if c.isalnum() else " " for c in self.label).split()
        if not words:
            return "stack"
        return words[0].lower() + "".join(w[:1].upper() + w[1:] for w in words[1:])


@dataclass(frozen=True)
class Certification:
    name: str
    issuer: str
    issued: int  # year
    expires: int | None = None  # year
    url: str = ""


@dataclass(frozen=True)
class Role:
    title: str
    org: str
    start: str  # YYYY-MM
    end: str | None  # YYYY-MM, None = current
    summary: str = ""


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
    stack: tuple[StackGroup, ...]
    links: tuple[tuple[str, str], ...]
    kind: str = "Engineer"
    work: Work | None = None
    feed_url: str | None = None
    certifications: tuple[Certification, ...] = ()
    experience: tuple[Role, ...] = ()
    featured: tuple[str, ...] = ()

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
        isinstance(k, str) and isinstance(v, str) and v.startswith(("https://", "mailto:"))
        for k, v in links.items()
    ):
        raise ConfigError("profile.links must map names to https:// or mailto: URLs")

    return Profile(
        login=raw["login"].strip(),
        handle=raw["handle"].strip(),
        display_name=raw["display_name"].strip(),
        tagline=raw["tagline"].strip(),
        role=raw["role"].strip(),
        region=raw["region"].strip(),
        timezone=raw["timezone"].strip(),
        focus=_str_list(raw, "focus"),
        stack=_stack(raw.get("stack")),
        links=tuple(links.items()),
        kind=_kind(raw.get("kind", "Engineer")),
        work=_work(raw.get("work")),
        feed_url=_https("feed_url", raw["feed_url"]) if raw.get("feed_url") else None,
        certifications=tuple(_cert(c) for c in _mappings(raw, "certifications")),
        experience=tuple(_role(r) for r in _mappings(raw, "experience")),
        featured=tuple(_repo_name(n) for n in _str_list(raw, "featured")),
    )


def _mappings(raw: dict, key: str) -> list[dict]:
    value = raw.get(key) or []
    if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
        raise ConfigError(f"profile.{key} must be a list of mappings")
    return value


def _year(key: str, value: object) -> int:
    if not isinstance(value, int) or not 1970 <= value <= 2100:
        raise ConfigError(f"profile.{key} must be a year like 2024")
    return value


def _month(key: str, value: object) -> str:
    text = str(value) if value is not None else ""
    parts = text.split("-")
    if len(parts) != 2 or not all(p.isdigit() for p in parts) or not 1 <= int(parts[1]) <= 12:
        raise ConfigError(f"profile.{key} must look like 2024-03")
    return text


def _cert(raw: dict) -> Certification:
    return Certification(
        name=_text("certifications.name", raw.get("name")),
        issuer=_text("certifications.issuer", raw.get("issuer")),
        issued=_year("certifications.issued", raw.get("issued")),
        expires=_year("certifications.expires", raw["expires"]) if raw.get("expires") else None,
        url=_https("certifications.url", raw["url"]) if raw.get("url") else "",
    )


def _role(raw: dict) -> Role:
    return Role(
        title=_text("experience.title", raw.get("title")),
        org=_text("experience.org", raw.get("org")),
        start=_month("experience.start", raw.get("start")),
        end=_month("experience.end", raw["end"]) if raw.get("end") else None,
        summary=_text("experience.summary", raw["summary"]) if raw.get("summary") else "",
    )


def _repo_name(value: str) -> str:
    owner, _, name = value.partition("/")
    if not owner or not name or "/" in name:
        raise ConfigError(f"profile.featured entries must look like owner/repo, got {value!r}")
    return value


def _stack(raw: object) -> tuple[StackGroup, ...]:
    """Either a flat list of tools or a mapping of group label -> list of tools."""
    if raw is None:
        return ()
    if isinstance(raw, list):
        return (StackGroup("", _str_list({"stack": raw}, "stack")),)
    if not isinstance(raw, dict):
        raise ConfigError("profile.stack must be a list or a mapping of group -> list")
    groups = []
    for label, items in raw.items():
        name = _text("stack group", label)
        groups.append(StackGroup(name, _str_list({f"stack.{name}": items}, f"stack.{name}")))
    return tuple(groups)


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
