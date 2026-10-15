from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from pulse import __main__ as cli
from pulse import readme

README = """# hi
<!-- pulse:hero --><!-- /pulse:hero -->
<!-- pulse:panels --><!-- /pulse:panels -->
<!-- pulse:writing --><!-- /pulse:writing -->
<!-- pulse:manifest -->
old
<!-- /pulse:manifest -->
<!-- pulse:links --><!-- /pulse:links -->
<!-- pulse:footer -->
x
<!-- /pulse:footer -->
"""


def test_replace_sections_is_idempotent():
    once = readme.replace_sections(README, {"manifest": "new", "links": "L", "footer": "F"})
    twice = readme.replace_sections(once, {"manifest": "new", "links": "L", "footer": "F"})
    assert once == twice
    assert "old" not in once
    assert "<!-- pulse:manifest -->\nnew\n<!-- /pulse:manifest -->" in once


def test_replace_sections_handles_backslashes():
    out = readme.replace_sections(README, {"manifest": r"C:\path\1"})
    assert r"C:\path\1" in out


def test_replace_sections_missing_marker():
    with pytest.raises(readme.MarkerError):
        readme.replace_sections("# empty", {"manifest": "x"})


def test_manifest_lists_only_public_recent_repos(snapshot, profile):
    text = readme.manifest(profile, snapshot)
    assert text.startswith("```yaml") and text.endswith("```")
    assert "recentlyShipped: [api]" in text
    assert "workload" not in text
    assert "octo/octo" not in text


def test_links_and_footer(snapshot, profile):
    assert readme.links(profile) == "[`github`](https://github.com/octo)"
    footer = readme.footer(snapshot)
    assert "2026-10-15 UTC" in footer
    assert "12:00" not in footer  # day-granular so idle runs don't create commits


@pytest.fixture
def workspace(tmp_path, snapshot):
    fixture = tmp_path / "snap.json"
    fixture.write_text(json.dumps(snapshot.to_dict()), encoding="utf-8")
    (tmp_path / "README.md").write_text(README, encoding="utf-8")
    shutil.copy(Path("profile.yml"), tmp_path / "profile.yml")
    return tmp_path


def _args(ws: Path) -> list[str]:
    return [
        "--profile",
        str(ws / "profile.yml"),
        "--out",
        str(ws / "assets"),
        "--readme",
        str(ws / "README.md"),
        "--fixture",
        str(ws / "snap.json"),
    ]


def test_cli_renders_all_assets_and_readme(workspace):
    assert cli.main([*_args(workspace), "--save-snapshot", str(workspace / "out.json")]) == 0
    files = sorted(p.name for p in (workspace / "assets").iterdir())
    assert len(files) == 34  # 17 panels x 2 themes; certs/experience off
    assert "status-dark.svg" in files and "pods-light.svg" in files
    assert "apiVersion: human.dev/v1" in (workspace / "README.md").read_text(encoding="utf-8")
    assert json.loads((workspace / "out.json").read_text())["login"] == "octo"


def test_cli_fails_cleanly_on_bad_profile(workspace):
    (workspace / "profile.yml").write_text("login: ''\n", encoding="utf-8")
    assert cli.main(_args(workspace)) == 1


def test_cli_requires_token_without_fixture(workspace, monkeypatch):
    monkeypatch.delenv("PULSE_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    args = _args(workspace)[:-2]
    assert cli.main(args) == 1


def test_validate_svg_rejects_bad_output():
    with pytest.raises(cli.RenderError, match="well-formed"):
        cli.validate_svg("x.svg", "<svg><g></svg>")
    with pytest.raises(cli.RenderError, match="limit"):
        cli.validate_svg("x.svg", "<svg>" + "a" * 200_000 + "</svg>")


def test_leak_check_blocks_private_names_without_echoing_them():
    with pytest.raises(cli.RenderError) as info:
        cli.check_for_leaks({"a.svg": "<svg>Acme/Secret</svg>"}, frozenset({"acme/secret"}))
    assert "acme/secret" not in str(info.value).lower()
    cli.check_for_leaks({"a.svg": "<svg>fine</svg>"}, frozenset({"acme/secret"}))


def test_cli_keeps_existing_panels_when_token_was_denied(workspace, snapshot):
    from dataclasses import replace

    denied = replace(snapshot, meta={**snapshot.meta, "denied": 30})
    (workspace / "snap.json").write_text(json.dumps(denied.to_dict()), encoding="utf-8")
    assert cli.main(_args(workspace)) == 1
    assert not (workspace / "assets").exists()
    assert cli.main([*_args(workspace), "--allow-partial"]) == 0
    assert (workspace / "assets").exists()


def test_small_denied_share_still_publishes(snapshot, caplog):
    from dataclasses import replace

    # 1 denied out of 4 PRs + 6 repos + 1 = 1/11 > 5% -> blocked; scale data up instead
    big = replace(snapshot, pull_requests=snapshot.pull_requests * 30, meta={"denied": 2})
    assert cli.denied_ratio(big) < 0.05
    cli.check_completeness(big)
    assert "refused" in caplog.text
    cli.check_completeness(replace(snapshot, meta={}))


def test_work_banner_and_manifest_escape_and_render(snapshot):
    from conftest import PROFILE_RAW

    from pulse.config import parse_profile

    raw = {
        **PROFILE_RAW,
        "kind": "DataScientist",
        "work": {
            "title": "Data Scientist",
            "company": "Acme <Labs>",
            "company_url": "https://acme.example/",
            "products": [{"name": "Lens", "url": "https://lens.example/", "summary": "LLM & k8s"}],
        },
    }
    profile = parse_profile(raw)
    banner = readme.work_banner(profile)
    assert "Acme &lt;Labs&gt;" in banner and "<Labs>" not in banner
    assert '<a href="https://lens.example/"><b>Lens</b></a> — LLM &amp; k8s' in banner
    text = readme.manifest(profile, snapshot)
    assert "kind: DataScientist" in text
    assert "employer: Acme <Labs>  # https://acme.example/" in text
    assert "    - Lens: LLM & k8s" in text


def test_work_banner_empty_without_work(profile):
    assert readme.work_banner(profile) == ""


def test_manifest_renders_grouped_stack(snapshot, profile):
    from conftest import PROFILE_RAW

    from pulse.config import parse_profile

    grouped = parse_profile({**PROFILE_RAW, "stack": {"MLOps": ["Kubeflow", "MLflow"]}})
    text = readme.manifest(grouped, snapshot)
    assert "  stack:\n    mlops: [Kubeflow, MLflow]" in text
    assert "  stack: [Go, Python]" in readme.manifest(profile, snapshot)


def test_hero_panels_and_writing_sections(snapshot, profile):
    from dataclasses import replace
    from datetime import date

    from pulse.models import Post

    hero = readme.hero(profile, {"status": "S", "activity": "A"})
    assert hero.count("<picture>") == 2
    block = readme.panels([("featured", "F"), ("pods", "P")], profile, snapshot)
    assert 'href="https://github.com/octo/api"' in block
    assert block.index("featured-light.svg") < block.index("octo/api") < block.index("pods")
    assert readme.writing(snapshot) == ""
    posts = (Post("A <b>post</b>", "https://x.example/a", date(2026, 9, 1)),)
    text = readme.writing(replace(snapshot, posts=posts))
    assert "A &lt;b&gt;post&lt;/b&gt;" in text and "Sep 01, 2026" in text


def test_token_expiry_warning(snapshot, capsys):
    from dataclasses import replace

    cli.warn_if_token_expiring(replace(snapshot, meta={"token_expires": "2026-10-25"}))
    assert "::warning::PULSE_TOKEN expires in 10 days" in capsys.readouterr().out
    cli.warn_if_token_expiring(replace(snapshot, meta={"token_expires": "2027-10-25"}))
    cli.warn_if_token_expiring(replace(snapshot, meta={"token_expires": "nonsense"}))
    assert capsys.readouterr().out == ""


def test_live_load_attaches_feed_posts(monkeypatch, tmp_path, snapshot):
    from pulse.config import parse_profile
    from pulse.github_client import FetchResult
    from pulse.models import Post

    monkeypatch.setenv("PULSE_TOKEN", "t")
    monkeypatch.setattr(cli, "fetch_snapshot", lambda *a: FetchResult(snapshot, frozenset()))
    monkeypatch.setattr(cli, "fetch_posts", lambda url: (Post("p", "https://x.example/p"),))
    from conftest import PROFILE_RAW

    args = cli.parse_args(["--readme", str(tmp_path / "R.md")])
    with_feed = parse_profile({**PROFILE_RAW, "feed_url": "https://x.example/rss"})
    assert cli.load_snapshot(args, with_feed).snapshot.posts[0].title == "p"
    assert cli.load_snapshot(args, parse_profile(PROFILE_RAW)).snapshot.posts == ()
