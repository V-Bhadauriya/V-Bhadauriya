from __future__ import annotations

from datetime import date

import httpx
import respx

from pulse.feed import fetch_posts, parse_feed

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>Serving LLMs with  KServe</title><link>https://blog.example/kserve</link>
        <pubDate>Tue, 01 Sep 2026 10:00:00 GMT</pubDate></item>
  <item><title>Insecure link</title><link>http://blog.example/x</link></item>
  <item><title></title><link>https://blog.example/empty</link></item>
  <item><title>No date</title><link>https://blog.example/nodate</link><pubDate>bad</pubDate></item>
</channel></rss>"""

ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><title>Kubeflow notes</title>
    <link rel="alternate" href="https://dev.example/kubeflow"/>
    <published>2026-08-02T00:00:00Z</published></entry>
  <entry><title>Only edit link</title><link rel="edit" href="https://dev.example/edit"/></entry>
</feed>"""

BOMB = """<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;">]>
<rss><channel><item><title>&lol2;</title></item></channel></rss>"""


def test_parse_rss_keeps_only_valid_https_posts():
    posts = parse_feed(RSS)
    assert [p.title for p in posts] == ["Serving LLMs with KServe", "No date"]
    assert posts[0].published == date(2026, 9, 1)
    assert posts[1].published is None


def test_parse_atom():
    posts = parse_feed(ATOM)
    assert len(posts) == 1
    assert posts[0].url == "https://dev.example/kubeflow"
    assert posts[0].published == date(2026, 8, 2)


@respx.mock
def test_fetch_posts_limits_and_never_raises():
    respx.get("https://blog.example/rss").mock(return_value=httpx.Response(200, text=RSS))
    assert len(fetch_posts("https://blog.example/rss", httpx.Client(), limit=1)) == 1

    respx.get("https://blog.example/down").mock(return_value=httpx.Response(500))
    assert fetch_posts("https://blog.example/down", httpx.Client()) == ()

    respx.get("https://blog.example/bomb").mock(return_value=httpx.Response(200, text=BOMB))
    assert fetch_posts("https://blog.example/bomb", httpx.Client()) == ()

    huge = "<rss>" + "x" * 2_100_000 + "</rss>"
    respx.get("https://blog.example/huge").mock(return_value=httpx.Response(200, text=huge))
    assert fetch_posts("https://blog.example/huge", httpx.Client()) == ()


@respx.mock
def test_redirects_must_stay_on_https_and_are_bounded():
    respx.get("https://blog.example/moved").mock(
        return_value=httpx.Response(301, headers={"location": "https://blog.example/rss2"})
    )
    respx.get("https://blog.example/rss2").mock(return_value=httpx.Response(200, text=RSS))
    assert len(fetch_posts("https://blog.example/moved", httpx.Client())) == 2

    internal = respx.get("http://169.254.169.254/latest").mock(return_value=httpx.Response(200))
    respx.get("https://blog.example/evil").mock(
        return_value=httpx.Response(302, headers={"location": "http://169.254.169.254/latest"})
    )
    assert fetch_posts("https://blog.example/evil", httpx.Client()) == ()
    assert not internal.called

    respx.get("https://blog.example/loop").mock(
        return_value=httpx.Response(302, headers={"location": "https://blog.example/loop"})
    )
    assert fetch_posts("https://blog.example/loop", httpx.Client()) == ()


@respx.mock
def test_declared_oversize_is_rejected_before_reading():
    respx.get("https://blog.example/big").mock(
        return_value=httpx.Response(200, headers={"content-length": "99999999"}, text="<rss/>")
    )
    assert fetch_posts("https://blog.example/big", httpx.Client()) == ()
