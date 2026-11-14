"""G08: the showcase runner sends five valid matchups and prints a ready export command."""

import httpx
import pytest

from app.models.matchup import Matchup
from scripts import run_showcase
from scripts.run_showcase import SHOWCASE, run_battle


def test_the_five_showcase_matchups_are_valid_and_in_plan_order() -> None:
    assert len(SHOWCASE) == 5
    for _title, body in SHOWCASE:
        Matchup.model_validate(body)  # raises if a field is wrong
    assert SHOWCASE[-1][1]["fighters"][0]["entity"] == "dragon"
    assert SHOWCASE[-1][1]["terrain"] == "open_field"


def fake_app(statuses: dict[str, list[str]]):
    started: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            battle_id = f"b-{len(started)}"
            started.append(battle_id)
            return httpx.Response(202, json={"battle_id": battle_id})
        battle_id = request.url.path.rsplit("/", 1)[-1]
        queue = statuses.get(battle_id, ["done"])
        return httpx.Response(200, json={"status": queue.pop(0) if len(queue) > 1 else queue[0]})

    return handler


def test_a_battle_is_followed_until_it_ends(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_showcase, "POLL_S", 0)
    handler = fake_app({"b-0": ["running", "running", "done"]})
    with httpx.Client(transport=httpx.MockTransport(handler), base_url="http://x") as client:
        assert run_battle(client, SHOWCASE[0][1]) == ("b-0", "done")


def test_main_prints_the_export_command_and_leaves_out_failures(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(run_showcase, "POLL_S", 0)
    handler = fake_app({"b-2": ["failed"]})
    real_client = httpx.Client

    def client(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), base_url="http://x")

    monkeypatch.setattr(run_showcase.httpx, "Client", client)
    assert run_showcase.main([]) == 1  # one battle failed
    out = capsys.readouterr().out
    assert "scripts.export_showcase" in out and "b-0=" in out
    assert "b-2=" not in out and "1 battle(s) didn't finish" in out
