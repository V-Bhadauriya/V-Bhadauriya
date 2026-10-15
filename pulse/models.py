"""Immutable domain models shared by the client, metrics and renderers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _opt_dt(value: str | None) -> datetime | None:
    return _dt(value) if value else None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


@dataclass(frozen=True)
class Language:
    name: str
    color: str
    size: int


@dataclass(frozen=True)
class Repo:
    """A repository. Private repos arrive here already anonymised (see privacy.py)."""

    name_with_owner: str
    is_private: bool
    is_fork: bool
    created_at: datetime
    pushed_at: datetime
    stars: int = 0
    languages: tuple[Language, ...] = ()

    @property
    def short_name(self) -> str:
        return self.name_with_owner.split("/")[-1]


@dataclass(frozen=True)
class Commit:
    repo: str
    is_private: bool
    committed_at: datetime
    additions: int = 0
    deletions: int = 0


@dataclass(frozen=True)
class PullRequest:
    repo: str
    is_private: bool
    created_at: datetime
    merged_at: datetime | None
    state: str


@dataclass(frozen=True)
class Day:
    day: date
    count: int


@dataclass(frozen=True)
class Snapshot:
    login: str
    name: str
    created_at: datetime
    fetched_at: datetime
    calendar: tuple[Day, ...] = ()
    repos: tuple[Repo, ...] = ()
    commits: tuple[Commit, ...] = ()
    pull_requests: tuple[PullRequest, ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        raw = asdict(self)
        return _jsonify(raw)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Snapshot:
        return cls(
            login=data["login"],
            name=data["name"],
            created_at=_dt(data["created_at"]),
            fetched_at=_dt(data["fetched_at"]),
            calendar=tuple(
                Day(date.fromisoformat(d["day"]), int(d["count"])) for d in data["calendar"]
            ),
            repos=tuple(
                Repo(
                    name_with_owner=r["name_with_owner"],
                    is_private=r["is_private"],
                    is_fork=r["is_fork"],
                    created_at=_dt(r["created_at"]),
                    pushed_at=_dt(r["pushed_at"]),
                    stars=r.get("stars", 0),
                    languages=tuple(Language(**lang) for lang in r.get("languages", [])),
                )
                for r in data["repos"]
            ),
            commits=tuple(
                Commit(
                    repo=c["repo"],
                    is_private=c["is_private"],
                    committed_at=_dt(c["committed_at"]),
                    additions=c.get("additions", 0),
                    deletions=c.get("deletions", 0),
                )
                for c in data["commits"]
            ),
            pull_requests=tuple(
                PullRequest(
                    repo=p["repo"],
                    is_private=p["is_private"],
                    created_at=_dt(p["created_at"]),
                    merged_at=_opt_dt(p.get("merged_at")),
                    state=p["state"],
                )
                for p in data["pull_requests"]
            ),
            meta=dict(data.get("meta", {})),
        )


def _jsonify(value: Any) -> Any:
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(v) for v in value]
    return value
