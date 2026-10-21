import os
import tempfile

import pytest
from starlette.websockets import WebSocketDisconnect

os.environ["CHESS_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")

from fastapi.testclient import TestClient  # noqa: E402

from backend.game import Game  # noqa: E402
from backend.main import app, hub  # noqa: E402

client = TestClient(app)


@pytest.fixture
def websocket_client():
    with TestClient(app) as test_client:
        yield test_client


def signup(name):
    r = client.post("/api/signup", json={"username": name, "password": "secret1"})
    assert r.status_code == 200
    return r.json()["token"]


def test_auth_flow():
    signup("alice")
    assert client.post("/api/signup", json={"username": "ALICE", "password": "secret1"}).status_code == 409
    assert client.post("/api/login", json={"username": "alice", "password": "bad"}).status_code == 401
    tok = client.post("/api/login", json={"username": "alice", "password": "secret1"}).json()["token"]
    assert client.get("/api/me", headers={"Authorization": "Bearer " + tok}).json()["username"] == "alice"


def test_game_rules():
    g = Game("x", "w", "b")
    assert g.move("b", "e7e5") == "Not your turn"
    assert g.move("w", "e2e5") == "Illegal move"
    assert g.move("w", "f2f3") is None
    g.move("b", "e7e5")
    g.move("w", "g2g4")
    g.move("b", "d8h4")
    assert g.result == "0-1"


def test_online_match(websocket_client):
    t1, t2 = signup("player1"), signup("player2")
    with websocket_client.websocket_connect(f"/ws?token={t1}") as a, websocket_client.websocket_connect(f"/ws?token={t2}") as b:
        assert a.receive_json()["type"] == "idle"
        assert b.receive_json()["type"] == "idle"
        a.send_json({"type": "find"})
        assert a.receive_json()["type"] == "waiting"
        b.send_json({"type": "find"})
        sa, sb = a.receive_json(), b.receive_json()
        a.receive_json(), b.receive_json()
        assert sa["white"] == "player1" and sb["black"] == "player2"
        a.send_json({"type": "move", "uci": "e2e4"})
        assert b.receive_json()["moves"] == ["e2e4"]
        b.receive_json()
        a.receive_json(), a.receive_json()


def test_opponent_presence(websocket_client):
    t1, t2 = signup("pres1"), signup("pres2")
    with websocket_client.websocket_connect(f"/ws?token={t1}") as a:
        assert a.receive_json()["type"] == "idle"
        with websocket_client.websocket_connect(f"/ws?token={t2}") as b:
            assert b.receive_json()["type"] == "idle"
            a.send_json({"type": "find"})
            a.receive_json()
            b.send_json({"type": "find"})
            a.receive_json(); a.receive_json()
            b.receive_json(); b.receive_json()
        assert a.receive_json() == {"type": "presence", "online": False}


def test_logout_closes_active_websocket(websocket_client):
    token = signup("logoutuser")
    with websocket_client.websocket_connect(f"/ws?token={token}") as ws:
        assert ws.receive_json()["type"] == "idle"
        response = websocket_client.post("/api/logout", headers={"Authorization": "Bearer " + token})
        assert response.status_code == 200
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 4401


def test_invalid_token_websocket_closes_with_4401(websocket_client):
    with websocket_client.websocket_connect("/ws?token=invalid") as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 4401


def test_duplicate_sockets_receive_game_updates(websocket_client):
    t1, t2 = signup("multi1"), signup("multi2")
    with websocket_client.websocket_connect(f"/ws?token={t1}") as first:
        assert first.receive_json()["type"] == "idle"
        with websocket_client.websocket_connect(f"/ws?token={t1}") as second:
            assert second.receive_json()["type"] == "idle"
            with websocket_client.websocket_connect(f"/ws?token={t2}") as opponent:
                assert opponent.receive_json()["type"] == "idle"
                first.send_json({"type": "find"})
                assert first.receive_json()["type"] == "waiting"
                assert second.receive_json()["type"] == "waiting"
                opponent.send_json({"type": "find"})
                assert first.receive_json()["type"] == "state"
                assert first.receive_json()["type"] == "presence"
                assert second.receive_json()["type"] == "state"
                assert second.receive_json()["type"] == "presence"
                assert opponent.receive_json()["type"] == "state"
                assert opponent.receive_json()["type"] == "presence"
                first.send_json({"type": "move", "uci": "e2e4"})
                assert second.receive_json()["moves"] == ["e2e4"]


def test_reconnect_reports_idle_or_waiting_state(websocket_client):
    token = signup("reconnect")
    with websocket_client.websocket_connect(f"/ws?token={token}") as first:
        assert first.receive_json()["type"] == "idle"
        first.send_json({"type": "find"})
        assert first.receive_json()["type"] == "waiting"
    with websocket_client.websocket_connect(f"/ws?token={token}") as second:
        assert second.receive_json()["type"] == "idle"
        second.send_json({"type": "find"})
        assert second.receive_json()["type"] == "waiting"
        with websocket_client.websocket_connect(f"/ws?token={token}") as duplicate:
            assert duplicate.receive_json()["type"] == "waiting"


def test_completed_games_are_removed_after_both_players_rematch(websocket_client):
    t1, t2 = signup("rematch1"), signup("rematch2")
    with websocket_client.websocket_connect(f"/ws?token={t1}") as first, websocket_client.websocket_connect(f"/ws?token={t2}") as second:
        assert first.receive_json()["type"] == "idle"
        assert second.receive_json()["type"] == "idle"
        first.send_json({"type": "find"})
        first.receive_json()
        second.send_json({"type": "find"})
        game1 = first.receive_json()["game_id"]
        first.receive_json()
        second.receive_json(); second.receive_json()
        first.send_json({"type": "resign"})
        first.receive_json(); first.receive_json()
        second.receive_json(); second.receive_json()
        first.send_json({"type": "find"})
        assert first.receive_json()["type"] == "waiting"
        second.send_json({"type": "find"})
        game2 = first.receive_json()["game_id"]
        assert game2 != game1
        first.receive_json()
        second.receive_json(); second.receive_json()
        assert game1 not in hub.games
