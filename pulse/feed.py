"""Latest posts from an RSS 2.0 or Atom feed (blog, Medium, dev.to, Substack...)."""

from __future__ import annotations

import logging
from datetime import date
from email.utils import parsedate_to_datetime

import httpx
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from pulse import config
from pulse.models import Post

log = logging.getLogger(__name__)

ATOM = "{http://www.w3.org/2005/Atom}"
MAX_FEED_BYTES = 2_000_000
MAX_REDIRECTS = 3
_REDIRECTS = {301, 302, 303, 307, 308}


class FeedError(RuntimeError):
    """The feed could not be fetched within the safety limits."""


def fetch_posts(url: str, http: httpx.Client | None = None, limit: int = 5) -> tuple[Post, ...]:
    """Never fails the run: a broken or oversized feed just means no posts this time."""
    client = http or httpx.Client(timeout=config.HTTP_TIMEOUT_S, follow_redirects=False)
    try:
        return parse_feed(download(client, url))[:limit]
    except (
        httpx.HTTPError,
        httpx.InvalidURL,
        httpx.StreamError,
        FeedError,
        ElementTree.ParseError,
        DefusedXmlException,
        UnicodeDecodeError,
    ) as exc:
        log.warning("could not read the writing feed (%s)", type(exc).__name__)
        return ()


def download(client: httpx.Client, url: str) -> str:
    """GET with manual redirects (https only, max 3) and a streamed size cap, so neither a
    redirect to an internal http:// host nor a huge (or gzip-bomb) body gets through."""
    for _ in range(MAX_REDIRECTS + 1):
        if not url.startswith("https://"):
            raise FeedError("feed URLs and redirects must use https")
        headers = {"User-Agent": config.USER_AGENT}
        with client.stream("GET", url, headers=headers) as response:
            if response.status_code in _REDIRECTS and "location" in response.headers:
                url = str(response.url.join(response.headers["location"]))
                continue
            response.raise_for_status()
            declared = response.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > MAX_FEED_BYTES:
                raise FeedError("feed is too large")
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > MAX_FEED_BYTES:
                    raise FeedError("feed is too large")
            return body.decode(response.encoding or "utf-8")
    raise FeedError("too many redirects")


def parse_feed(xml: str) -> tuple[Post, ...]:
    root = ElementTree.fromstring(xml)
    items = root.findall("./channel/item") or root.findall(f"{ATOM}entry")
    posts = (_rss_item(i) if i.tag == "item" else _atom_entry(i) for i in items)
    return tuple(p for p in posts if p is not None)


def _rss_item(item) -> Post | None:
    return _post(
        item.findtext("title"),
        item.findtext("link"),
        _rfc822_date(item.findtext("pubDate")),
    )


def _atom_entry(entry) -> Post | None:
    links = entry.findall(f"{ATOM}link")
    href = next(
        (link.get("href") for link in links if link.get("rel", "alternate") == "alternate"),
        None,
    )
    stamp = entry.findtext(f"{ATOM}published") or entry.findtext(f"{ATOM}updated")
    return _post(entry.findtext(f"{ATOM}title"), href, _iso_date(stamp))


def _post(title: str | None, url: str | None, published: date | None) -> Post | None:
    title = " ".join((title or "").split())
    url = (url or "").strip()
    if not title or not url.startswith("https://"):
        return None
    return Post(title=title[:120], url=url, published=published)


def _rfc822_date(value: str | None) -> date | None:
    try:
        return parsedate_to_datetime(value).date() if value else None
    except (TypeError, ValueError):
        return None


def _iso_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value.strip()[:10]) if value else None
    except ValueError:
        return None
