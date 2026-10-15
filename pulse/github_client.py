"""GitHub GraphQL client and snapshot assembly."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from importlib import resources
from typing import Any

import httpx

from pulse import config
from pulse.models import Commit, Day, Language, PullRequest, Repo, Snapshot
from pulse.privacy import alias, build_alias_map

log = logging.getLogger(__name__)

_RETRY_STATUS = {429, 500, 502, 503, 504}


class GitHubError(RuntimeError):
    """Raised when the GitHub API cannot satisfy a request."""


def load_query(name: str) -> str:
    return resources.files("pulse.queries").joinpath(f"{name}.graphql").read_text("utf-8")


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class GitHubClient:
    def __init__(
        self,
        token: str,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not token:
            raise GitHubError("a GitHub token is required (set PULSE_TOKEN or GITHUB_TOKEN)")
        self._http = http or httpx.Client(timeout=config.HTTP_TIMEOUT_S)
        self._headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": config.USER_AGENT,
        }
        self._sleep = sleep
        self._denied = 0

    @property
    def denied(self) -> int:
        """How many resources GitHub refused to return to this token so far."""
        return self._denied

    def query(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        payload = {"query": query, "variables": variables}
        last_error = "unknown error"
        for attempt in range(1, config.MAX_RETRIES + 1):
            try:
                response = self._http.post(config.GRAPHQL_URL, json=payload, headers=self._headers)
            except httpx.HTTPError as exc:
                last_error = f"transport error: {type(exc).__name__}"
                rate_wait = None
            else:
                if response.status_code == 200:
                    return self._unwrap(response.json())
                if response.status_code in (401, 403) and not _is_rate_limited(response):
                    raise GitHubError(f"GitHub rejected the token (HTTP {response.status_code})")
                if response.status_code not in _RETRY_STATUS and not _is_rate_limited(response):
                    raise GitHubError(f"GitHub API returned HTTP {response.status_code}")
                last_error = f"HTTP {response.status_code}"
                rate_wait = _rate_limit_wait(response)
            if attempt < config.MAX_RETRIES:
                backoff = config.RETRY_BACKOFF_S * 4 ** (attempt - 1)
                delay = rate_wait if rate_wait is not None else backoff
                log.warning("GitHub request failed (%s); retrying in %.0fs", last_error, delay)
                self._sleep(delay)
        raise GitHubError(f"GitHub API failed after {config.MAX_RETRIES} attempts: {last_error}")

    def _unwrap(self, body: dict[str, Any]) -> dict[str, Any]:
        errors = body.get("errors") or []
        data = body.get("data")
        if errors:
            # Only fixed categories are reported: GitHub's messages can name private repos/orgs,
            # and Actions logs on a public profile repo are world-readable.
            categories = [classify_error(e) for e in errors]
            self._denied += sum(1 for c in categories if c in _ACCESS_DENIED)
            kinds = ", ".join(sorted(set(categories)))
            if not data:
                raise GitHubError(f"GraphQL error ({len(errors)}x: {kinds})")
            # Partial data (e.g. an org blocks token access to one repo) is still useful.
            log.warning("GraphQL returned partial data (%dx: %s)", len(errors), kinds)
        if data is None:
            raise GitHubError("GraphQL response contained no data")
        return data


_ERROR_CATEGORIES = (
    ("saml", "SSO_NOT_AUTHORIZED"),
    ("personal access tokens (classic)", "CLASSIC_TOKEN_BLOCKED_BY_ORG"),
    ("fine-grained", "FINE_GRAINED_TOKEN_POLICY"),
    ("oauth app access restrictions", "OAUTH_APP_RESTRICTED"),
    ("ip allow list", "IP_ALLOW_LIST"),
)
_ACCESS_DENIED = {category for _, category in _ERROR_CATEGORIES} | {"FORBIDDEN"}


def classify_error(error: dict[str, Any]) -> str:
    """Map a GraphQL error to a fixed, name-free category that is safe to log publicly."""
    message = str(error.get("message", "")).lower()
    for needle, category in _ERROR_CATEGORIES:
        if needle in message:
            return category
    kind = str(error.get("type", "UNKNOWN")).upper()
    return kind if kind.replace("_", "").isalpha() else "UNKNOWN"


def _rate_limit_wait(response: httpx.Response) -> float | None:
    """Seconds to wait before retrying a rate-limited response, capped."""
    if not _is_rate_limited(response):
        return None
    retry_after = response.headers.get("retry-after", "")
    if retry_after.isdigit():
        return min(float(retry_after), config.MAX_RATE_LIMIT_WAIT_S)
    reset = response.headers.get("x-ratelimit-reset", "")
    if reset.isdigit():
        return min(max(float(reset) - time.time(), 1.0), config.MAX_RATE_LIMIT_WAIT_S)
    return config.MAX_RATE_LIMIT_WAIT_S / 2


def _is_rate_limited(response: httpx.Response) -> bool:
    return response.status_code in (403, 429) and (
        response.headers.get("x-ratelimit-remaining") == "0"
        or "secondary rate limit" in response.text.lower()
    )


# --------------------------------------------------------------------------- fetchers


def fetch_user(client: GitHubClient, login: str, now: datetime) -> dict[str, Any]:
    since = now - timedelta(days=config.LOOKBACK_DAYS)
    data = client.query(
        load_query("user"),
        {"login": login, "from": since.isoformat(), "to": now.isoformat()},
    )
    user = data.get("user")
    if not user:
        raise GitHubError(f"GitHub user not found: {login}")
    return user


def fetch_repos(client: GitHubClient, login: str) -> list[dict[str, Any]]:
    return list(_paginate(client, "repos", {"login": login}, ("user", "repositories")))


def fetch_pull_requests(client: GitHubClient, login: str, since: datetime) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for node in _paginate(client, "pull_requests", {"login": login}, ("user", "pullRequests")):
        if _parse_dt(node["createdAt"]) < since or len(collected) >= config.MAX_PULL_REQUESTS:
            break
        collected.append(node)
    return collected


def _paginate(
    client: GitHubClient, query_name: str, variables: dict[str, Any], path: tuple[str, ...]
) -> Iterator[dict[str, Any]]:
    query = load_query(query_name)
    cursor: str | None = None
    for _ in range(config.MAX_PAGES):
        data = client.query(query, {**variables, "cursor": cursor})
        connection = data
        for key in path:
            connection = (connection or {}).get(key) or {}
        yield from (n for n in connection.get("nodes") or [] if n)
        page = connection.get("pageInfo") or {}
        next_cursor = page.get("endCursor")
        if not page.get("hasNextPage") or not next_cursor or next_cursor == cursor:
            return
        cursor = next_cursor
    log.warning("stopped paginating %s after %d pages", query_name, config.MAX_PAGES)


_REPO_FIELDS = (
    "nameWithOwner isPrivate isFork createdAt pushedAt stargazerCount "
    "languages(first: 8, orderBy: {field: SIZE, direction: DESC}) "
    "{ edges { size node { name color } } }"
)


def build_repo_details_query(count: int) -> str:
    params = ", ".join(f"$o{i}: String!, $n{i}: String!" for i in range(count))
    body = "\n".join(
        f"  r{i}: repository(owner: $o{i}, name: $n{i}) {{ {_REPO_FIELDS} }}" for i in range(count)
    )
    return f"query RepoDetails({params}) {{\n{body}\n}}"


def fetch_repo_details(client: GitHubClient, names: list[str]) -> list[dict[str, Any]]:
    """Metadata for repos you contribute to that the owner-affiliation listing leaves out
    (e.g. org repos reached through team membership)."""
    found: list[dict[str, Any]] = []
    for start in range(0, len(names), config.REPO_BATCH_SIZE):
        batch = names[start : start + config.REPO_BATCH_SIZE]
        variables: dict[str, Any] = {}
        for i, name in enumerate(batch):
            owner, repo = name.split("/", 1)
            variables.update({f"o{i}": owner, f"n{i}": repo})
        data = client.query(build_repo_details_query(len(batch)), variables)
        found = [*found, *(data[f"r{i}"] for i in range(len(batch)) if data.get(f"r{i}"))]
    return found


def contributed_repo_names(user: dict[str, Any], pr_nodes: list[dict[str, Any]]) -> list[str]:
    """Every repo with your commits or PRs in the window, in first-seen order."""
    by_commits = [
        (entry.get("repository") or {}).get("nameWithOwner")
        for entry in (user.get("contributionsCollection") or {}).get(
            "commitContributionsByRepository"
        )
        or []
    ]
    by_prs = [p["repository"]["nameWithOwner"] for p in pr_nodes]
    return list(dict.fromkeys(name for name in [*by_commits, *by_prs] if name))


_HISTORY_SELECTION = (
    "defaultBranchRef { target { ... on Commit { "
    "history(first: %(page)d, after: $c%(i)d, since: $since, author: {id: $author}) { "
    "pageInfo { hasNextPage endCursor } nodes { committedDate additions deletions } "
    "} } } }"
)


def build_history_query(count: int) -> str:
    """Aliased history query for `count` repos; owner/name/cursor are passed as variables."""
    params = ", ".join(f"$o{i}: String!, $n{i}: String!, $c{i}: String" for i in range(count))
    selections = (
        _HISTORY_SELECTION % {"i": i, "page": config.HISTORY_PAGE_SIZE} for i in range(count)
    )
    body = "\n".join(
        f"  r{i}: repository(owner: $o{i}, name: $n{i}) {{ {sel} }}"
        for i, sel in enumerate(selections)
    )
    return f"query History($author: ID!, $since: GitTimestamp!, {params}) {{\n{body}\n}}"


def fetch_commits(
    client: GitHubClient, author_id: str, repo_names: list[str], since: datetime
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    """Commit nodes per repo (paginated up to a cap) and the number of unreadable repos."""
    result: dict[str, list[dict[str, Any]]] = {name: [] for name in repo_names}
    unreadable: set[str] = set()
    pending: list[tuple[str, str | None]] = [(name, None) for name in repo_names]
    while pending:
        size = config.HISTORY_BATCH_SIZE
        batch, pending = pending[:size], pending[size:]
        variables: dict[str, Any] = {"author": author_id, "since": since.isoformat()}
        for i, (name, cursor) in enumerate(batch):
            owner, repo = name.split("/", 1)
            variables.update({f"o{i}": owner, f"n{i}": repo, f"c{i}": cursor})
        data = client.query(build_history_query(len(batch)), variables)
        for i, (name, _) in enumerate(batch):
            if not data.get(f"r{i}"):
                unreadable.add(name)
            history = _history_of(data.get(f"r{i}"))
            nodes = [n for n in history.get("nodes") or [] if n]
            result[name] = [*result[name], *nodes]
            page = history.get("pageInfo") or {}
            if page.get("hasNextPage") and len(result[name]) < config.MAX_COMMITS_PER_REPO:
                pending = [*pending, (name, page.get("endCursor"))]
    if unreadable:
        log.warning("%d repositories were not readable with this token", len(unreadable))
    return result, len(unreadable)


def _history_of(repo: dict[str, Any] | None) -> dict[str, Any]:
    ref = (repo or {}).get("defaultBranchRef") or {}
    return (ref.get("target") or {}).get("history") or {}


# --------------------------------------------------------------------------- assembly


@dataclass(frozen=True)
class FetchResult:
    snapshot: Snapshot
    # Real private names, kept in memory only so outputs can be scanned for leaks.
    private_names: frozenset[str]


def fetch_snapshot(client: GitHubClient, login: str, now: datetime) -> FetchResult:
    since = now - timedelta(days=config.LOOKBACK_DAYS)
    user = fetch_user(client, login, now)
    listed = fetch_repos(client, login)
    pr_nodes = fetch_pull_requests(client, login, since)

    known = {r["nameWithOwner"] for r in listed}
    extra = [n for n in contributed_repo_names(user, pr_nodes) if n not in known]
    repo_nodes = [*listed, *fetch_repo_details(client, extra)]

    active = [r["nameWithOwner"] for r in repo_nodes if _parse_dt(r["pushedAt"]) >= since]
    commit_nodes, unreadable = fetch_commits(client, user["id"], active, since)

    snapshot = build_snapshot(user, repo_nodes, pr_nodes, commit_nodes, now)
    private_names = frozenset(
        [r["nameWithOwner"] for r in repo_nodes if r["isPrivate"]]
        + [p["repository"]["nameWithOwner"] for p in pr_nodes if p["repository"]["isPrivate"]]
    )
    meta = {**snapshot.meta, "unreadable_repos": unreadable, "denied": client.denied}
    return FetchResult(replace(snapshot, meta=meta), private_names)


def build_snapshot(
    user: dict[str, Any],
    repo_nodes: list[dict[str, Any]],
    pr_nodes: list[dict[str, Any]],
    commit_nodes: dict[str, list[dict[str, Any]]],
    now: datetime,
) -> Snapshot:
    """Convert raw API nodes into an anonymised, immutable Snapshot."""
    private_names = [r["nameWithOwner"] for r in repo_nodes if r["isPrivate"]] + [
        p["repository"]["nameWithOwner"] for p in pr_nodes if p["repository"]["isPrivate"]
    ]
    aliases = build_alias_map(private_names)
    privacy = {r["nameWithOwner"]: r["isPrivate"] for r in repo_nodes}

    repos = tuple(_repo(r, aliases) for r in repo_nodes)
    commits = tuple(
        Commit(
            repo=alias(name, privacy.get(name, True), aliases),
            is_private=privacy.get(name, True),
            committed_at=_parse_dt(node["committedDate"]),
            additions=int(node.get("additions") or 0),
            deletions=int(node.get("deletions") or 0),
        )
        for name, nodes in commit_nodes.items()
        for node in nodes
    )
    pulls = tuple(
        PullRequest(
            repo=alias(p["repository"]["nameWithOwner"], p["repository"]["isPrivate"], aliases),
            is_private=p["repository"]["isPrivate"],
            created_at=_parse_dt(p["createdAt"]),
            merged_at=_parse_dt(p["mergedAt"]) if p.get("mergedAt") else None,
            state=p["state"],
        )
        for p in pr_nodes
    )
    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    calendar = tuple(
        Day(date.fromisoformat(d["date"]), int(d["contributionCount"]))
        for w in weeks
        for d in w["contributionDays"]
    )
    return Snapshot(
        login=user["login"],
        name=user.get("name") or user["login"],
        created_at=_parse_dt(user["createdAt"]),
        fetched_at=now,
        calendar=calendar,
        repos=repos,
        commits=commits,
        pull_requests=pulls,
        meta={"private_repos": len(aliases)},
    )


def _repo(node: dict[str, Any], aliases: dict[str, str]) -> Repo:
    edges = (node.get("languages") or {}).get("edges") or []
    return Repo(
        name_with_owner=alias(node["nameWithOwner"], node["isPrivate"], aliases),
        is_private=node["isPrivate"],
        is_fork=node["isFork"],
        created_at=_parse_dt(node["createdAt"]),
        pushed_at=_parse_dt(node["pushedAt"]),
        stars=int(node.get("stargazerCount") or 0),
        languages=tuple(
            Language(e["node"]["name"], e["node"].get("color") or "#8b949e", int(e["size"]))
            for e in edges
        ),
    )
