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
    assert result.private_names == frozenset({"secretcorp/top-secret", "teamorg/platform"})
    # three active repos x two history pages
    assert len(snap.commits) == 6
    # PR older than the lookback window is dropped
    assert len(snap.pull_requests) == 1
    assert snap.meta == {"private_repos": 2, "unreadable_repos": 0, "denied": 0}
    dumped = json.dumps(snap.to_dict())
    assert "secretcorp" not in dumped and "top-secret" not in dumped
    assert "teamorg" not in dumped
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
