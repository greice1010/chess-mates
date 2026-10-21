import asyncio
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth
from .game import Game

app = FastAPI(title="Chess Mates")
auth.init_db()


class Credentials(BaseModel):
    username: str
    password: str


@app.post("/api/signup")
def signup(c: Credentials):
    if not auth.USERNAME_RE.match(c.username):
        raise HTTPException(400, "Username must be 3-20 letters, digits or underscores")
    if len(c.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    if not auth.create_user(c.username, c.password):
        raise HTTPException(409, "Username already taken")
    return {"token": auth.create_session(c.username), "username": c.username}


@app.post("/api/login")
def login(c: Credentials):
    name = auth.verify_user(c.username, c.password)
    if not name:
        raise HTTPException(401, "Invalid username or password")
    return {"token": auth.create_session(name), "username": name}


@app.get("/api/me")
def me(authorization: str = Header(default="")):
    name = auth.user_for_token(authorization.removeprefix("Bearer "))
    if not name:
        raise HTTPException(401, "Not authenticated")
    return {"username": name}


@app.post("/api/logout")
async def logout(authorization: str = Header(default="")):
    token = authorization.removeprefix("Bearer ")
    auth.delete_session(token)
    await hub.revoke(token)
    return {"ok": True}


class Hub:
    """In-memory matchmaking and live games."""

    def __init__(self):
        self.sockets: dict[str, set[WebSocket]] = {}
        self.sessions: dict[str, set[WebSocket]] = {}
        self.socket_users: dict[WebSocket, str] = {}
        self.socket_tokens: dict[WebSocket, str] = {}
        self.games: dict[str, Game] = {}
        self.player_game: dict[str, str] = {}
        self.waiting: str | None = None

    async def send(self, user: str, msg: dict):
        for ws in tuple(self.sockets.get(user, ())):
            try:
                await ws.send_json(msg)
            except Exception:
                pass

    def connect(self, user: str, token: str, ws: WebSocket):
        self.sockets.setdefault(user, set()).add(ws)
        self.sessions.setdefault(token, set()).add(ws)
        self.socket_users[ws] = user
        self.socket_tokens[ws] = token

    async def revoke(self, token: str):
        sockets = self.sessions.pop(token, set())
        changed_users = set()
        for ws in sockets:
            user = self.socket_users.pop(ws, None)
            self.socket_tokens.pop(ws, None)
            if user:
                self.sockets[user].discard(ws)
                if not self.sockets[user]:
                    del self.sockets[user]
                    changed_users.add(user)
            try:
                await ws.close(code=4401)
            except RuntimeError:
                pass
        for user in changed_users:
            gid = self.player_game.get(user)
            if gid:
                await self.presence(self.games[gid])

    def cleanup_game(self, game_id: str):
        if game_id not in self.player_game.values():
            self.games.pop(game_id, None)

    async def presence(self, game: Game):
        for name in game.players.values():
            opp = next(n for n in game.players.values() if n != name)
            await self.send(name, {"type": "presence", "online": opp in self.sockets})

    async def broadcast(self, game: Game):
        for name in game.players.values():
            await self.send(name, game.state())
        await self.presence(game)

    async def find(self, user: str):
        gid = self.player_game.get(user)
        if gid and not self.games[gid].result:
            await self.send(user, self.games[gid].state())
            return
        if self.waiting == user:
            return
        if self.waiting and self.waiting in self.sockets:
            opp, self.waiting = self.waiting, None
            game = Game(uuid.uuid4().hex[:8], opp, user)
            self.games[game.id] = game
            old_games = {self.player_game[name] for name in (opp, user) if name in self.player_game}
            self.player_game[opp] = self.player_game[user] = game.id
            for old_game in old_games:
                self.cleanup_game(old_game)
            await self.broadcast(game)
        else:
            self.waiting = user
            await self.send(user, {"type": "waiting"})

    async def handle(self, user: str, msg: dict):
        kind = msg.get("type")
        if kind == "find":
            await self.find(user)
        elif kind == "cancel" and self.waiting == user:
            self.waiting = None
            await self.send(user, {"type": "idle"})
        elif kind in ("move", "resign"):
            game = self.games.get(self.player_game.get(user, ""))
            if not game:
                return await self.send(user, {"type": "error", "message": "No active game"})
            if kind == "resign":
                game.resign(user)
            else:
                err = game.move(user, str(msg.get("uci", "")))
                if err:
                    return await self.send(user, {"type": "error", "message": err})
            await self.broadcast(game)

    async def disconnect(self, user: str, ws: WebSocket):
        self.socket_users.pop(ws, None)
        token = self.socket_tokens.pop(ws, None)
        if token:
            self.sessions.get(token, set()).discard(ws)
            if not self.sessions.get(token):
                self.sessions.pop(token, None)
        sockets = self.sockets.get(user)
        if sockets:
            sockets.discard(ws)
            if not sockets:
                del self.sockets[user]
        if self.waiting == user and user not in self.sockets:
            self.waiting = None
        if user not in self.sockets:
            gid = self.player_game.get(user)
            if gid:
                await self.presence(self.games[gid])


hub = Hub()


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket, token: str = ""):
    user = auth.user_for_token(token)
    await ws.accept()
    if not user:
        await ws.close(code=4401)
        return
    hub.connect(user, token, ws)
    gid = hub.player_game.get(user)
    if gid:
        await ws.send_json(hub.games[gid].state())
        await hub.presence(hub.games[gid])
    elif hub.waiting == user:
        await ws.send_json({"type": "waiting"})
    else:
        await ws.send_json({"type": "idle"})
    try:
        while True:
            msg = await ws.receive_json()
            if auth.user_for_token(token) != user or ws not in hub.socket_users:
                await ws.close(code=4401)
                break
            if isinstance(msg, dict):
                await hub.handle(user, msg)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await hub.disconnect(user, ws)


FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
