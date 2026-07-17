from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import install_api, make_lifespan
from app.persistence.database import Database


def frontend_config(player_count: int = 8) -> dict[str, Any]:
    players = [
        {
            "id": "hero" if index == 1 else f"p{index}",
            "name": "Ryanchl" if index == 1 else f"Joueur {index}",
            "seat": index,
            "stack": 1_000,
            "initial_profile": "unknown" if index == 1 else "tag",
        }
        for index in range(1, player_count + 1)
    ]
    if player_count == 2:
        dealer, small, big = "hero", "hero", "p2"
    else:
        dealer = "hero" if player_count == 3 else f"p{player_count - 2}"
        small = f"p{player_count - 1}"
        big = f"p{player_count}"
    return {
        "player_count": player_count,
        "players": players,
        "unit": "chips",
        "small_blind": 5,
        "big_blind": 10,
        "ante": 0,
        "ante_type": "classic",
        "game_mode": "cash",
        "dealer_id": dealer,
        "small_blind_id": small,
        "big_blind_id": big,
        "blind_levels": [],
        "advice_mode": "immediate",
    }


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = FastAPI(lifespan=make_lifespan(Database(tmp_path / "api.sqlite3")))
    install_api(app)
    with TestClient(app) as test_client:
        yield test_client


def test_frontend_contract_creates_eight_player_table(client: TestClient) -> None:
    response = client.post("/api/sessions", json=frontend_config(8))
    assert response.status_code == 201
    table = response.json()
    assert set(table) == {
        "session_id",
        "config",
        "hand",
        "players",
        "legal_actions",
        "selector",
        "advice",
        "persistence_status",
    }
    assert len(table["players"]) == 8
    assert table["hand"]["active_player_id"] == "hero"
    assert table["hand"]["phase"] == "playing"
    assert table["selector"]["next_slot"] == "hero_1"
    assert table["config"]["player_count"] == 8
    assert table["config"]["advice_mode"] == "immediate"
    assert all("hole_cards" not in player for player in table["players"] if player["id"] != "hero")


def test_frontend_configuration_round_trips_unit_and_quiz_mode(client: TestClient) -> None:
    config = frontend_config(2)
    config.update(
        {
            "unit": "big_blinds",
            "small_blind": 50,
            "big_blind": 100,
            "advice_mode": "quiz",
        }
    )
    for player in config["players"]:
        player["stack"] = 10_000

    table = client.post("/api/sessions", json=config).json()
    assert table["config"]["unit"] == "big_blinds"
    assert table["config"]["small_blind"] == 0.5
    assert table["config"]["big_blind"] == 1
    assert table["config"]["players"][0]["stack"] == 100
    assert table["config"]["advice_mode"] == "quiz"


def test_create_cards_action_save_export_and_restore(client: TestClient) -> None:
    table = client.post("/api/sessions", json=frontend_config(3)).json()
    session_id = table["session_id"]
    assert (
        client.post(
            f"/api/sessions/{session_id}/cards", json={"slot": "hero_1", "card": "As"}
        ).status_code
        == 200
    )
    table = client.post(
        f"/api/sessions/{session_id}/cards", json={"slot": "hero_2", "card": "Kd"}
    ).json()
    assert table["hand"]["hero_cards"] == ["As", "Kd"]
    action = client.post(f"/api/sessions/{session_id}/actions", json={"action": "call"})
    assert action.status_code == 200
    saved = client.post(f"/api/sessions/{session_id}/save", json={})
    assert saved.status_code == 200
    exported = client.get(f"/api/sessions/{session_id}/export").json()
    client.delete(f"/api/sessions/{session_id}")
    imported = client.post("/api/import", json=exported)
    assert imported.status_code == 200
    assert imported.json() == {"imported": True, "session_id": session_id}
    restored = client.get(f"/api/sessions/{session_id}/state").json()
    assert restored["hand"]["hero_cards"] == ["As", "Kd"]
    assert len(restored["hand"]["action_log"]) == 1


def test_advice_history_detail_csv_and_exit_report(client: TestClient) -> None:
    table = client.post("/api/sessions", json=frontend_config(3)).json()
    session_id = table["session_id"]
    for slot, card in (("hero_1", "As"), ("hero_2", "Ad")):
        client.post(f"/api/sessions/{session_id}/cards", json={"slot": slot, "card": card})
    advice_response = client.post(
        f"/api/sessions/{session_id}/advice",
        json={"level": "fast", "trials": 100, "seed": 7},
    )
    assert advice_response.status_code == 200
    advice = advice_response.json()
    assert advice["final"]["is_exact"] is False
    assert advice["estimated_equity"] > 0
    client.post(f"/api/sessions/{session_id}/actions", json={"action": "call"})
    history = client.get(f"/api/history?session_id={session_id}").json()
    assert isinstance(history, list) and len(history) == 1
    detail = client.get(f"/api/history/{history[0]['id']}").json()
    assert detail["known_cards"] == ["As", "Ad"]
    assert detail["table_state"]["hand"]["active_player_id"] == "hero"
    csv_response = client.get("/api/history/export?format=csv")
    assert csv_response.status_code == 200
    assert "final_advice" in csv_response.text
    report = client.post(f"/api/sessions/{session_id}/exit", json={}).json()
    assert report["session_id"] == session_id
    assert report["decisions"] == 1


def test_delayed_explanation_never_blocks_action_and_stays_associated(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("POKER_IA_EXPLANATION_DELAY_MS", "250")
    table = client.post("/api/sessions", json=frontend_config(3)).json()
    session_id = table["session_id"]
    for slot, card in (("hero_1", "As"), ("hero_2", "Kd")):
        client.post(f"/api/sessions/{session_id}/cards", json={"slot": slot, "card": card})
    started = time.perf_counter()
    advice = client.post(
        f"/api/sessions/{session_id}/advice", json={"trials": 100, "seed": 9}
    ).json()
    elapsed = time.perf_counter() - started
    assert elapsed < 0.8
    assert advice["explanation_pending"] is True
    advice_id = advice["id"]
    action_started = time.perf_counter()
    assert (
        client.post(f"/api/sessions/{session_id}/actions", json={"action": "call"}).status_code
        == 200
    )
    assert time.perf_counter() - action_started < 0.2
    time.sleep(0.35)
    detail = client.get(f"/api/history/{advice_id}").json()
    assert "Aucun nouveau calcul" in detail["detailed_explanation"]
    assert detail["id"] == advice_id


def test_opponent_patch_reset_export_import(client: TestClient) -> None:
    table = client.post("/api/sessions", json=frontend_config(3)).json()
    session_id = table["session_id"]
    patched = client.patch(
        "/api/opponents/p2",
        json={"notes": "Suit trop au flop", "adaptation_enabled": False},
    ).json()
    assert patched["notes"] == "Suit trop au flop"
    assert patched["adaptation_enabled"] is False
    client.post(f"/api/sessions/{session_id}/actions", json={"action": "call"})
    persisted = client.get("/api/opponents/p2").json()
    assert persisted["adaptation_enabled"] is False
    exported = client.get("/api/opponents/p2/export").json()
    assert client.post("/api/opponents/import", json=exported).status_code == 200
    reset = client.post("/api/opponents/p2/reset", json={}).json()
    assert reset["hands_observed"] == 0


def test_restart_hand_endpoint_matches_undo_schema_and_resets_hand(client: TestClient) -> None:
    table = client.post("/api/sessions", json=frontend_config(3)).json()
    session_id = table["session_id"]
    for slot, card in (("hero_1", "As"), ("hero_2", "Kd")):
        client.post(f"/api/sessions/{session_id}/cards", json={"slot": slot, "card": card})
    assert (
        client.post(f"/api/sessions/{session_id}/actions", json={"action": "call"}).status_code
        == 200
    )
    undo_response = client.post(f"/api/sessions/{session_id}/undo")
    assert undo_response.status_code == 200
    undo_keys = set(undo_response.json())

    restart_response = client.post(f"/api/sessions/{session_id}/restart-hand")
    assert restart_response.status_code == 200
    restarted = restart_response.json()
    assert set(restarted) == undo_keys
    assert restarted["hand"]["hero_cards"] == []
    assert restarted["hand"]["board"] == []
    assert restarted["hand"]["active_player_id"] == "hero"
    assert restarted["hand"]["phase"] == "playing"


def test_replace_player_endpoint_matches_patch_player_schema(client: TestClient) -> None:
    table = client.post("/api/sessions", json=frontend_config(3)).json()
    session_id = table["session_id"]
    patch_response = client.patch(
        f"/api/sessions/{session_id}/players/p3", json={"notes": "note de test"}
    )
    assert patch_response.status_code == 200
    patch_keys = set(patch_response.json())

    replace_response = client.post(
        f"/api/sessions/{session_id}/players/p2/replace",
        json={"name": "Nouveau Joueur", "initial_profile": "loose_aggressive"},
    )
    assert replace_response.status_code == 200
    replaced = replace_response.json()
    assert set(replaced) == patch_keys
    player = next(item for item in replaced["players"] if item["id"] == "p2")
    assert player["name"] == "Nouveau Joueur"
    assert player["profile"]["hands_observed"] == 0


def test_replace_player_mid_hand_shows_new_name_in_state(client: TestClient) -> None:
    """Régression: en cours de main, le nom vit dans player_overrides et la vue
    d'état doit l'appliquer (le moteur n'est pas reconstruit après une action)."""
    table = client.post("/api/sessions", json=frontend_config(3)).json()
    session_id = table["session_id"]
    action = client.post(f"/api/sessions/{session_id}/actions", json={"action": "call"})
    assert action.status_code == 200

    replace_response = client.post(
        f"/api/sessions/{session_id}/players/p2/replace",
        json={"name": "Remplaçant"},
    )
    assert replace_response.status_code == 200
    player = next(item for item in replace_response.json()["players"] if item["id"] == "p2")
    assert player["name"] == "Remplaçant"
    assert player["profile"]["hands_observed"] == 0

    state = client.get(f"/api/sessions/{session_id}/state").json()
    player_state = next(item for item in state["players"] if item["id"] == "p2")
    assert player_state["name"] == "Remplaçant"


def test_seat_endpoints_remove_and_queue_new_player(client: TestClient) -> None:
    table = client.post("/api/sessions", json=frontend_config(3)).json()
    session_id = table["session_id"]

    removed_response = client.delete(f"/api/sessions/{session_id}/players/p2/seat")
    assert removed_response.status_code == 200
    removed = next(item for item in removed_response.json()["players"] if item["id"] == "p2")
    assert removed["status"] == "away"
    assert removed["pending_join"] is False

    seated_response = client.post(
        f"/api/sessions/{session_id}/players/p2/seat",
        json={"name": "Jordan", "stack": 800, "initial_profile": "unknown"},
    )
    assert seated_response.status_code == 200
    seated = next(item for item in seated_response.json()["players"] if item["id"] == "p2")
    assert seated["name"] == "Jordan"
    assert seated["stack"] == 800
    assert seated["status"] == "away"
    assert seated["pending_join"] is True


def test_patch_stack_mid_hand_is_visible_immediately(client: TestClient) -> None:
    table = client.post("/api/sessions", json=frontend_config(3)).json()
    session_id = table["session_id"]
    assert (
        client.post(f"/api/sessions/{session_id}/actions", json={"action": "call"}).status_code
        == 200
    )

    response = client.patch(f"/api/sessions/{session_id}/players/p2", json={"stack": 777})
    assert response.status_code == 200
    player = next(item for item in response.json()["players"] if item["id"] == "p2")
    assert player["stack"] == 777


def test_replace_player_endpoint_refuses_hero(client: TestClient) -> None:
    table = client.post("/api/sessions", json=frontend_config(3)).json()
    session_id = table["session_id"]
    response = client.post(
        f"/api/sessions/{session_id}/players/hero/replace",
        json={"name": "Quelqu'un d'autre"},
    )
    assert response.status_code == 422
    assert "principal" in response.json()["detail"]
