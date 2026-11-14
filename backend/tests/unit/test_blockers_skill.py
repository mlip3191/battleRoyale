"""Tests for the team /blockers skill (.claude/skills/blockers/blockers.py, #214).

The script is read-only and calls `gh`; these tests never run the real `gh` or touch the network.
The encoding tests pin the Windows fix from #211: `gh` prints UTF-8, but Windows Python decodes
and prints with cp1252 unless told otherwise. Windows decoding is simulated by the fake
`subprocess.run` below (`windows_run`), so these tests behave the same on every OS; they don't
prove a real Windows machine works.
"""

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "blockers" / "blockers.py"

TEAM_TABLE = """# Decisions

## Team

| Name | GitHub | OS | Lane |
|---|---|---|---|
| José Núñez (PM) | `jnunez` | Windows | 1 — Platform |
| Adam Fondale | `afondale` | Windows | 2 — Intake |
| Dillon Smart | `dilloncsmart` | Windows | 5 — Front end |
"""


# Load the script as a module; .claude/ isn't a package, so import it by path.
@pytest.fixture
def blockers() -> ModuleType:
    spec = importlib.util.spec_from_file_location("blockers_skill", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# A repo-like folder with the Team table, so load_team() has something to read.
@pytest.fixture
def team_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "DECISIONS.md").write_text(TEAM_TABLE, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


# A stand-in for subprocess.run that decodes like Windows: cp1252 unless the caller asks otherwise.
def windows_run(stdout: bytes, returncode: int = 0, stderr: bytes = b"") -> Any:
    def run(args: list[str], *, capture_output: bool, text: bool, **kwargs: Any) -> Any:
        encoding = kwargs.get("encoding") or "cp1252"
        errors = kwargs.get("errors") or "strict"
        return subprocess.CompletedProcess(
            args, returncode, stdout.decode(encoding, errors), stderr.decode(encoding, errors)
        )

    return run


def test_blocked_by_reads_issue_numbers_and_ignores_prose(blockers: ModuleType) -> None:
    assert blockers.blocked_by("**Blocked by:** #12, #14 (the parser)") == {12, 14}
    assert blockers.blocked_by("Nothing is blocked by safety here.") == set()
    assert blockers.blocked_by("") == set()


def test_closes_reads_every_closing_keyword(blockers: ModuleType) -> None:
    body = "Closes #3. Fixes #4, and resolves #5. Part of #6."
    assert blockers.closes(body) == {3, 4, 5}


def test_label_value_reads_a_prefixed_label(blockers: ModuleType) -> None:
    assert blockers.label_value(["type: chore", "wave: 4"], "wave") == "4"
    assert blockers.label_value(["type: chore"], "wave") is None


def test_tier_for_is_p0_when_someone_is_waiting(blockers: ModuleType) -> None:
    assert blockers.tier_for(1, [42]) == 0
    assert blockers.tier_for(1, []) == 1
    assert blockers.tier_for(2, []) == 2


def test_load_team_reads_names_and_the_pm_as_utf8(blockers: ModuleType, team_dir: Path) -> None:
    names, pm = blockers.load_team()
    assert names == {"jnunez": "José", "afondale": "Adam", "dilloncsmart": "Dillon"}
    assert pm == "jnunez"


# "Á" is UTF-8 C3 81; byte 0x81 has no cp1252 character, which is what crashed on Windows (#211).
def test_gh_output_is_read_as_utf8_on_windows(
    blockers: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    reply = '[{"title": "Á fight 🔴"}]'.encode()
    monkeypatch.setattr(blockers.subprocess, "run", windows_run(reply))
    assert blockers.gh("pr", "list") == [{"title": "Á fight 🔴"}]


def test_a_missing_gh_says_so_in_plain_english(
    blockers: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(*args: Any, **kwargs: Any) -> Any:
        raise FileNotFoundError("gh")

    monkeypatch.setattr(blockers.subprocess, "run", missing)
    with pytest.raises(SystemExit, match="isn't installed"):
        blockers.gh("api", "user")


def test_a_logged_out_gh_says_to_run_auth_login(
    blockers: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    stderr = b"To get started with GitHub CLI, please run:  gh auth login"
    monkeypatch.setattr(blockers.subprocess, "run", windows_run(b"", returncode=4, stderr=stderr))
    with pytest.raises(SystemExit, match="not logged in"):
        blockers.gh("api", "user")


# One open PR waiting on the person running it, one waiting on a teammate; titles have non-ASCII.
def fake_gh(*args: str) -> Any:
    def pr(number: int, author: str, reviewer: str, title: str) -> dict[str, Any]:
        return {
            "number": number,
            "title": title,
            "author": {"login": author},
            "isDraft": False,
            "baseRefName": "main",
            "headRefName": f"branch-{number}",
            "reviewDecision": "",
            "reviews": [],
            "reviewRequests": [{"login": reviewer}],
            "statusCheckRollup": [],
            "mergeable": "MERGEABLE",
            "commits": [],
            "body": "",
            "updatedAt": "2026-11-11T00:00:00Z",
        }

    if args[0] == "api":
        return {"login": "dilloncsmart"}
    if args[0] == "pr" and "open" in args:
        return [
            pr(1, "jnunez", "afondale", "Á new arena"),
            pr(2, "jnunez", "dilloncsmart", "Café 🔴"),
        ]
    return []


def test_main_prints_on_a_windows_console_with_you_first(
    blockers: ModuleType, team_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    console = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", console)
    monkeypatch.setattr(sys, "argv", ["blockers.py"])
    monkeypatch.setattr(blockers, "gh", fake_gh)

    blockers.main()

    console.flush()
    out = console.buffer.getvalue().decode("utf-8")
    assert "🟠 P1" in out
    assert out.index("**Dillon** (you)") < out.index("**Adam**")
    assert "PR #2: first review (by José). *Café 🔴*" in out


# A teammate's PR that touches a critical file, so "Critical files approval" fails until the PM
# approves. `reviews` and `commits` vary per test (#277).
def critical_pr(reviews: list[dict[str, Any]], commits: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "number": 9,
        "title": "Edit ARCHITECTURE",
        "author": {"login": "afondale"},
        "isDraft": False,
        "baseRefName": "main",
        "headRefName": "branch-9",
        "reviewDecision": "",
        "reviews": reviews,
        "reviewRequests": [],
        "statusCheckRollup": [{"name": "Critical files approval", "conclusion": "FAILURE"}],
        "mergeable": "MERGEABLE",
        "commits": commits,
        "body": "",
        "updatedAt": "2026-11-11T00:00:00Z",
    }


def review(state: str, at: str) -> dict[str, Any]:
    return {"author": {"login": "jnunez"}, "state": state, "submittedAt": at}


def commit(headline: str, at: str) -> dict[str, Any]:
    return {"messageHeadline": headline, "committedDate": at}


# Run the script with --json on one critical-files PR; return each person's actions on it.
def actions_for(
    blockers: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: Any, pr: dict[str, Any]
) -> dict[str, list[str]]:
    monkeypatch.setattr(sys, "argv", ["blockers.py", "--json", "--as", "jnunez"])
    monkeypatch.setattr(blockers, "gh", lambda *args: [pr] if args[:2] == ("pr", "list") else [])
    blockers.main()
    out: dict[str, list[str]] = {}
    for item in json.loads(capsys.readouterr().out)["items"]:
        out.setdefault(item["who"], []).append(item["action"])
    return out


FIRST = commit("Edit ARCHITECTURE", "2026-11-10T10:00:00Z")


def test_no_pm_review_yet_asks_the_pm_to_review_and_approve(
    blockers: ModuleType, team_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    actions = actions_for(blockers, monkeypatch, capsys, critical_pr([], [FIRST]))
    assert actions["jnunez"] == ["review + approve (touches critical files)"]


def test_a_pm_changes_request_with_no_push_leaves_the_pm_out(
    blockers: ModuleType, team_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    pr = critical_pr([review("CHANGES_REQUESTED", "2026-11-10T12:00:00Z")], [FIRST])
    actions = actions_for(blockers, monkeypatch, capsys, pr)
    assert "jnunez" not in actions
    assert actions["afondale"] == ["address José's changes request"]


def test_a_push_after_the_changes_request_gives_the_pm_one_re_review(
    blockers: ModuleType, team_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    fix = commit("Fix the review", "2026-11-11T09:00:00Z")
    pr = critical_pr([review("CHANGES_REQUESTED", "2026-11-10T12:00:00Z")], [FIRST, fix])
    actions = actions_for(blockers, monkeypatch, capsys, pr)
    assert len(actions["jnunez"]) == 1
    assert actions["jnunez"][0].startswith("re-review (fixes pushed after your changes request")


def test_a_merge_only_push_still_leaves_the_pm_out(
    blockers: ModuleType, team_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    merge = commit("Merge remote-tracking branch 'origin/main'", "2026-11-11T09:00:00Z")
    pr = critical_pr([review("CHANGES_REQUESTED", "2026-11-10T12:00:00Z")], [FIRST, merge])
    actions = actions_for(blockers, monkeypatch, capsys, pr)
    assert "jnunez" not in actions


def test_a_push_after_the_pm_approved_asks_for_a_re_approval(
    blockers: ModuleType, team_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    later = commit("One more fix", "2026-11-11T09:00:00Z")
    pr = critical_pr([review("APPROVED", "2026-11-10T12:00:00Z")], [FIRST, later])
    actions = actions_for(blockers, monkeypatch, capsys, pr)
    assert actions["jnunez"] == [
        "re-approve on the latest commit, then re-run the critical-files check"
    ]
