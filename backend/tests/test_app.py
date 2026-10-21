import os
import tempfile

os.environ["CHESS_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")

from fastapi.testclient import TestClient  # noqa: E402

from backend.game import Game  # noqa: E402
from backend.main import app  # noqa: E402

client = TestClient(app)


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


def test_online_match():
    t1, t2 = signup("player1"), signup("player2")
    with client.websocket_connect(f"/ws?token={t1}") as a, client.websocket_connect(f"/ws?token={t2}") as b:
        a.send_json({"type": "find"})
        assert a.receive_json()["type"] == "waiting"
        b.send_json({"type": "find"})
        sa, sb = a.receive_json(), b.receive_json()
        assert sa["white"] == "player1" and sb["black"] == "player2"
        a.send_json({"type": "move", "uci": "e2e4"})
        assert b.receive_json()["moves"] == ["e2e4"]
        a.receive_json()
