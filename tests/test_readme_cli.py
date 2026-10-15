from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from pulse import __main__ as cli
from pulse import readme

README = """# hi
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
    assert len(files) == 16
    assert "status-dark.svg" in files and "pods-light.svg" in files
    assert "kind: Engineer" in (workspace / "README.md").read_text(encoding="utf-8")
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
