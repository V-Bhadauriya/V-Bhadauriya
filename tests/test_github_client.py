from __future__ import annotations

import json

import httpx
import pytest
import respx
from conftest import NOW

from pulse import config
from pulse.github_client import (
    GitHubClient,
    GitHubError,
    build_history_query,
    build_snapshot,
    classify_error,
    fetch_repos,
    fetch_snapshot,
)

URL = config.GRAPHQL_URL


@pytest.fixture
def client():
    return GitHubClient("t0ken", http=httpx.Client(), sleep=lambda _s: None)


def test_requires_token():
    with pytest.raises(GitHubError, match="token"):
        GitHubClient("")


@respx.mock
def test_query_returns_data_and_sends_auth(client):
    route = respx.post(URL).mock(return_value=httpx.Response(200, json={"data": {"ok": 1}}))
    assert client.query("{ ok }", {}) == {"ok": 1}
    assert route.calls[0].request.headers["Authorization"] == "Bearer t0ken"


@respx.mock
def test_query_tolerates_partial_errors_without_logging_messages(client, caplog):
    body = {"data": {"ok": 1}, "errors": [{"type": "FORBIDDEN", "message": "acme/secret-x"}]}
    respx.post(URL).mock(return_value=httpx.Response(200, json=body))
    assert client.query("{ ok }", {}) == {"ok": 1}
    assert "FORBIDDEN" in caplog.text
    assert "secret-x" not in caplog.text
    assert client.denied == 1


@pytest.mark.parametrize(
    "error, category",
    [
        (
            {
                "type": "FORBIDDEN",
                "message": "Resource protected by organization SAML enforcement. "
                "You must grant your Personal Access token access to acme.",
            },
            "SSO_NOT_AUTHORIZED",
        ),
        (
            {
                "type": "FORBIDDEN",
                "message": "`acme` forbids access via a personal access tokens "
                "(classic). Please use a GitHub App...",
            },
            "CLASSIC_TOKEN_BLOCKED_BY_ORG",
        ),
        (
            {
                "type": "FORBIDDEN",
                "message": "Although you appear to have the correct authorization "
                "credentials, the `acme` organization has enabled OAuth App access restrictions",
            },
            "OAUTH_APP_RESTRICTED",
        ),
        ({"type": "NOT_FOUND", "message": "Could not resolve acme/x"}, "NOT_FOUND"),
        ({"type": "<b>weird</b>", "message": ""}, "UNKNOWN"),
        ({}, "UNKNOWN"),
    ],
)
def test_classify_error_is_name_free(error, category):
    result = classify_error(error)
    assert result == category
    assert "acme" not in result.lower()


@respx.mock
def test_rate_limit_honours_retry_after():
    waits: list[float] = []
    client = GitHubClient("t", http=httpx.Client(), sleep=waits.append)
    limited = httpx.Response(429, headers={"retry-after": "30"}, text="secondary rate limit")
    respx.post(URL).mock(side_effect=[limited, httpx.Response(200, json={"data": {"ok": 1}})])
    assert client.query("{ ok }", {}) == {"ok": 1}
    assert waits == [30.0]


@respx.mock
def test_rate_limit_wait_is_capped():
    waits: list[float] = []
    client = GitHubClient("t", http=httpx.Client(), sleep=waits.append)
    limited = httpx.Response(
        403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "99999999999"}
    )
    respx.post(URL).mock(side_effect=[limited, httpx.Response(200, json={"data": {"ok": 1}})])
    client.query("{ ok }", {})
    assert waits == [config.MAX_RATE_LIMIT_WAIT_S]


@respx.mock
def test_pagination_stops_on_missing_cursor(client):
    page = {"pageInfo": {"hasNextPage": True, "endCursor": None}, "nodes": [{"x": 1}]}
    route = respx.post(URL).mock(
        return_value=httpx.Response(200, json={"data": {"user": {"repositories": page}}})
    )
    assert fetch_repos(client, "octo") == [{"x": 1}]
    assert route.call_count == 1


@respx.mock
def test_query_raises_on_errors_without_data(client):
    errors = [{"type": "NOT_FOUND", "message": "Could not resolve 'acme/secret-repo'"}]
    respx.post(URL).mock(return_value=httpx.Response(200, json={"data": None, "errors": errors}))
    with pytest.raises(GitHubError, match="NOT_FOUND") as info:
        client.query("{ ok }", {})
    # GitHub's message text can name private repos and must never surface.
    assert "secret-repo" not in str(info.value)


@respx.mock
def test_query_rejects_bad_token_without_retry(client):
    route = respx.post(URL).mock(return_value=httpx.Response(401, text="nope"))
    with pytest.raises(GitHubError, match="rejected"):
        client.query("{ ok }", {})
    assert route.call_count == 1


@respx.mock
def test_query_fails_fast_on_unexpected_status(client):
    respx.post(URL).mock(return_value=httpx.Response(418))
    with pytest.raises(GitHubError, match="418"):
        client.query("{ ok }", {})


@respx.mock
def test_query_retries_transient_failures(client):
    route = respx.post(URL).mock(
        side_effect=[
            httpx.Response(502),
            httpx.ConnectError("boom"),
            httpx.Response(200, json={"data": {"ok": 2}}),
        ]
    )
    assert client.query("{ ok }", {}) == {"ok": 2}
    assert route.call_count == 3


@respx.mock
def test_query_retries_rate_limit_then_gives_up(client):
    limited = httpx.Response(403, headers={"x-ratelimit-remaining": "0"}, text="limit")
    route = respx.post(URL).mock(return_value=limited)
    with pytest.raises(GitHubError, match="attempts"):
        client.query("{ ok }", {})
    assert route.call_count == config.MAX_RETRIES


def test_history_query_uses_variables_not_interpolation():
    query = build_history_query(2)
    assert "r0: repository(owner: $o0, name: $n0)" in query
    assert "r1: repository(owner: $o1, name: $n1)" in query
    assert "after: $c1" in query


# ------------------------------------------------------------------ end-to-end fetch

USER = {
    "id": "U1",
    "login": "octo",
    "name": "Octo",
    "createdAt": "2018-10-18T00:00:00Z",
    "contributionsCollection": {
        "commitContributionsByRepository": [
            {"repository": {"nameWithOwner": "octo/api"}},
            {"repository": {"nameWithOwner": "teamorg/platform"}},
        ],
        "contributionCalendar": {
            "weeks": [{"contributionDays": [{"date": "2026-10-14", "contributionCount": 3}]}]
        },
    },
}

REPOS = [
    {
        "nameWithOwner": "octo/api",
        "isPrivate": False,
        "isFork": False,
        "createdAt": "2025-01-01T00:00:00Z",
        "pushedAt": "2026-10-14T00:00:00Z",
        "stargazerCount": 4,
        "languages": {"edges": [{"size": 100, "node": {"name": "Go", "color": None}}]},
    },
    {
        "nameWithOwner": "secretcorp/top-secret",
        "isPrivate": True,
        "isFork": False,
        "createdAt": "2025-01-01T00:00:00Z",
        "pushedAt": "2026-10-13T00:00:00Z",
        "stargazerCount": 0,
        "languages": None,
    },
    {
        "nameWithOwner": "octo/ancient",
        "isPrivate": False,
        "isFork": False,
        "createdAt": "2015-01-01T00:00:00Z",
        "pushedAt": "2016-01-01T00:00:00Z",
        "stargazerCount": 0,
        "languages": {"edges": []},
    },
]

PRS = [
    {
        "createdAt": "2026-10-10T00:00:00Z",
        "mergedAt": "2026-10-10T02:00:00Z",
        "state": "MERGED",
        "repository": {"nameWithOwner": "secretcorp/top-secret", "isPrivate": True},
    },
    {
        "createdAt": "2020-01-01T00:00:00Z",
        "mergedAt": None,
        "state": "CLOSED",
        "repository": {"nameWithOwner": "octo/api", "isPrivate": False},
    },
]


def _history(nodes, has_next=False, cursor=None):
    return {
        "defaultBranchRef": {
            "target": {
                "history": {
                    "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
                    "nodes": nodes,
                }
            }
        }
    }


def _fake_github(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    query, variables = body["query"], body["variables"]
    if query.startswith("query User"):
        return httpx.Response(200, json={"data": {"user": USER, "rateLimit": {}}})
    if query.startswith("query Repos"):
        page = {
            "pageInfo": {"hasNextPage": variables["cursor"] is None, "endCursor": "p2"},
            "nodes": REPOS[:2] if variables["cursor"] is None else REPOS[2:],
        }
        return httpx.Response(200, json={"data": {"user": {"repositories": page}}})
    if query.startswith("query PullRequests"):
        page = {"pageInfo": {"hasNextPage": False}, "nodes": PRS}
        return httpx.Response(200, json={"data": {"user": {"pullRequests": page}}})
    if query.startswith("query Reviews"):
        nodes = [
            {
                "createdAt": "2026-10-10T00:00:00Z",
                "repository": {"nameWithOwner": "reviewco/secret-svc", "isPrivate": True},
                "reviews": {"nodes": [{"submittedAt": "2026-10-10T03:00:00Z"}]},
            },
            {"createdAt": "2026-10-11T00:00:00Z", "repository": None, "reviews": None},
            {
                "createdAt": "2026-10-11T00:00:00Z",
                "repository": {"nameWithOwner": "octo/api", "isPrivate": False},
                "reviews": {"nodes": []},
            },
        ]
        page = {"pageInfo": {"hasNextPage": False}, "nodes": nodes}
        return httpx.Response(200, json={"data": {"search": page}})
    if query.startswith("query RepoDetails"):
        data = {}
        for i in range(10):
            if f"n{i}" not in variables:
                break
            name = f"{variables[f'o{i}']}/{variables[f'n{i}']}"
            data[f"r{i}"] = {**REPOS[0], "nameWithOwner": name, "isPrivate": True}
        return httpx.Response(200, json={"data": data})
    if query.startswith("query History"):
        data = {}
        for i in range(10):
            if f"n{i}" not in variables:
                break
            commit = {"committedDate": "2026-10-12T05:00:00Z", "additions": 1, "deletions": 0}
            first_page = variables[f"c{i}"] is None
            data[f"r{i}"] = _history([commit], has_next=first_page, cursor="h2")
        return httpx.Response(200, json={"data": data})
    return httpx.Response(400)


@respx.mock
def test_fetch_snapshot_end_to_end_anonymises_private_repos(client):
    respx.post(URL).mock(side_effect=_fake_github)
    result = fetch_snapshot(client, "octo", NOW)
    snap = result.snapshot

    assert snap.login == "octo"
    # 3 listed + 1 org repo reached only via contributions (team membership)
    assert len(snap.repos) == 4
    assert result.private_names == frozenset(
        {"secretcorp/top-secret", "teamorg/platform", "reviewco/secret-svc"}
    )
    # one usable review (the others lack a repo or a submitted review)
    assert len(snap.reviews) == 1 and snap.reviews[0].is_private
    # three active repos x two history pages
    assert len(snap.commits) == 6
    # PR older than the lookback window is dropped
    assert len(snap.pull_requests) == 1
    assert snap.meta == {
        "private_repos": 3,
        "unreadable_repos": 0,
        "denied": 0,
        "token_expires": None,
    }
    dumped = json.dumps(snap.to_dict())
    assert "secretcorp" not in dumped and "top-secret" not in dumped
    assert "teamorg" not in dumped and "reviewco" not in dumped
    assert snap.repos[0].languages[0].color == "#8b949e"


def test_build_snapshot_unknown_repo_commits_are_treated_private():
    snap = build_snapshot(
        USER,
        [],
        [],
        {"ghost/repo": [{"committedDate": "2026-10-12T05:00:00Z"}]},
        NOW,
    )
    assert snap.commits[0].is_private
    assert "ghost" not in snap.commits[0].repo


@respx.mock
def test_fetch_user_missing(client):
    respx.post(URL).mock(return_value=httpx.Response(200, json={"data": {"user": None}}))
    with pytest.raises(GitHubError, match="not found"):
        fetch_snapshot(client, "nobody", NOW)


@respx.mock
def test_unreadable_repos_are_counted(client):
    def handler(request):
        body = json.loads(request.content)
        if body["query"].startswith("query History"):
            errors = [{"type": "FORBIDDEN", "message": "SAML enforcement"}]
            return httpx.Response(200, json={"data": {"r0": None}, "errors": errors})
        return _fake_github(request)

    respx.post(URL).mock(side_effect=handler)
    result = fetch_snapshot(client, "octo", NOW)
    assert result.snapshot.meta["unreadable_repos"] >= 1
    assert result.snapshot.meta["denied"] >= 1


@respx.mock
def test_token_expiry_header_is_recorded(client):
    headers = {"github-authentication-token-expiration": "2026-11-01 00:00:00 UTC"}
    respx.post(URL).mock(
        return_value=httpx.Response(200, json={"data": {"ok": 1}}, headers=headers)
    )
    client.query("{ ok }", {})
    assert client.token_expires == "2026-11-01"


def test_parse_token_expiry():
    from pulse.github_client import parse_token_expiry

    assert parse_token_expiry("2026-12-31 00:00:00 -0800") == "2026-12-31"
    assert parse_token_expiry("") is None
    assert parse_token_expiry("garbage!!") is None


def test_private_free_text_is_dropped():
    pr_nodes = [
        {
            "title": "Fix secret billing bug for BigCustomer",
            "createdAt": "2026-10-10T00:00:00Z",
            "mergedAt": None,
            "state": "OPEN",
            "repository": {"nameWithOwner": "corp/billing", "isPrivate": True},
        },
        {
            "title": "docs: readme",
            "createdAt": "2026-10-10T00:00:00Z",
            "mergedAt": None,
            "state": "OPEN",
            "repository": {"nameWithOwner": "octo/api", "isPrivate": False},
        },
    ]
    repos = [
        {**REPOS[0]},
        {
            **REPOS[1],
            "nameWithOwner": "corp/billing",
            "description": "internal billing",
            "latestRelease": {"tagName": "v9", "publishedAt": "2026-01-01T00:00:00Z"},
        },
    ]
    commits = {
        "corp/billing": [{"committedDate": "2026-10-10T00:00:00Z", "messageHeadline": "secret"}],
        "octo/api": [{"committedDate": "2026-10-10T00:00:00Z", "messageHeadline": "feat: x"}],
    }
    snap = build_snapshot(USER, repos, pr_nodes, commits, NOW)
    dumped = json.dumps(snap.to_dict())
    for secret in ("BigCustomer", "internal billing", "v9", '"secret"', "corp/"):
        assert secret not in dumped
    assert "docs: readme" in dumped and "feat: x" in dumped


def test_reviews_before_window_are_ignored_and_times_are_utc():
    old_and_new = [
        {
            "createdAt": "2024-01-01T00:00:00Z",
            "repository": {"nameWithOwner": "octo/api", "isPrivate": False},
            "reviews": {"nodes": [{"submittedAt": "2024-01-02T00:00:00Z"}]},
        },
        {
            "createdAt": "2026-10-01T00:00:00Z",
            "repository": {"nameWithOwner": "octo/api", "isPrivate": False},
            "reviews": {"nodes": [{"submittedAt": "2026-10-01T23:30:00-05:00"}]},
        },
    ]
    snap = build_snapshot(USER, [REPOS[0]], [], {}, NOW, old_and_new)
    assert len(snap.reviews) == 1
    assert snap.reviews[0].reviewed_at.isoformat() == "2026-10-02T04:30:00+00:00"


def test_alias_numbers_do_not_depend_on_result_order():
    a = {**REPOS[1], "nameWithOwner": "corp/a"}
    b = {**REPOS[1], "nameWithOwner": "corp/b"}
    first = build_snapshot(USER, [a, b], [], {}, NOW)
    second = build_snapshot(USER, [b, a], [], {}, NOW)
    assert {r.name_with_owner for r in first.repos} == {r.name_with_owner for r in second.repos}
    assert first.repos[0].name_with_owner == second.repos[1].name_with_owner


def test_public_text_mentioning_private_repo_is_blanked():
    from pulse.github_client import public_text_scrubber

    scrub = public_text_scrubber({"corp/billing-core": "private/workload-01", "corp/api": "x"})
    assert scrub("bump billing-core to v2") == ""
    assert scrub("Billing-Core fix") == ""
    assert scrub("billing-corex unrelated") == "billing-corex unrelated"
    assert scrub("api docs") == "api docs"  # short names are not scrubbed
    assert scrub(None) == ""
    assert public_text_scrubber({})("anything") == "anything"
