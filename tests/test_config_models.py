from __future__ import annotations

import json

import pytest
from conftest import PROFILE_RAW

from pulse.config import ConfigError, load_profile, parse_profile
from pulse.models import Snapshot
from pulse.privacy import PRIVATE_PREFIX, alias, build_alias_map, is_anonymised


def test_parse_profile_valid(profile):
    assert profile.login == "octo"
    assert profile.stack == ("Go", "Python")
    assert profile.links == (("github", "https://github.com/octo"),)
    assert profile.tz.key == "America/Los_Angeles"


@pytest.mark.parametrize(
    "patch, message",
    [
        ({"login": ""}, "login"),
        ({"timezone": "Mars/Base"}, "timezone"),
        ({"links": {"site": "http://insecure"}}, "links"),
        ({"stack": "Go"}, "stack"),
        ({"tagline": "```\nbreakout"}, "backticks"),
        ({"focus": ["ok", "`x`"]}, "backticks"),
        ({"kind": "Data Scientist"}, "kind"),
        ({"work": "nope"}, "work"),
        ({"work": {"title": "DS", "company": "A", "company_url": "http://x"}}, "company_url"),
        ({"work": {"title": "", "company": "A", "company_url": "https://x"}}, "work.title"),
        (
            {"work": {"title": "DS", "company": "A", "company_url": "https://x", "products": [1]}},
            "products",
        ),
    ],
)
def test_parse_profile_rejects_invalid(patch, message):
    with pytest.raises(ConfigError, match=message):
        parse_profile({**PROFILE_RAW, **patch})


def test_parse_profile_rejects_non_mapping():
    with pytest.raises(ConfigError):
        parse_profile(["not", "a", "mapping"])


def test_load_profile_missing_and_invalid(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_profile(tmp_path / "missing.yml")
    bad = tmp_path / "bad.yml"
    bad.write_text("login: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigError, match="YAML"):
        load_profile(bad)


def test_load_profile_real_file():
    profile = load_profile(__import__("pathlib").Path("profile.yml"))
    assert profile.login == "V-Bhadauriya"
    assert profile.work is not None and profile.work.products[0].name == "NirikshaAI"


def test_snapshot_round_trip(snapshot):
    restored = Snapshot.from_dict(json.loads(json.dumps(snapshot.to_dict())))
    assert restored == snapshot


def test_alias_map_is_stable_and_deduplicated():
    aliases = build_alias_map(["acme/secret", "acme/secret", "acme/other"])
    assert aliases == {
        "acme/secret": f"{PRIVATE_PREFIX}01",
        "acme/other": f"{PRIVATE_PREFIX}02",
    }


def test_alias_never_leaks_unknown_private_name():
    assert alias("acme/secret", True, {}) == f"{PRIVATE_PREFIX}00"
    assert alias("octo/public", False, {}) == "octo/public"
    assert is_anonymised(f"{PRIVATE_PREFIX}07")
    assert not is_anonymised("octo/public")
