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
def logout(authorization: str = Header(default="")):
    auth.delete_session(authorization.removeprefix("Bearer "))
    return {"ok": True}


class Hub:
    """In-memory matchmaking and live games."""

    def __init__(self):
        self.sockets: dict[str, WebSocket] = {}
        self.games: dict[str, Game] = {}
        self.player_game: dict[str, str] = {}
        self.waiting: str | None = None

    async def send(self, user: str, msg: dict):
        ws = self.sockets.get(user)
        if ws:
            try:
                await ws.send_json(msg)
            except Exception:
                pass

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
            self.player_game[opp] = self.player_game[user] = game.id
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
        if self.sockets.get(user) is not ws:
            return
        del self.sockets[user]
        if self.waiting == user:
            self.waiting = None
        gid = self.player_game.get(user)
        if gid:
            await self.presence(self.games[gid])


hub = Hub()


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket, token: str = ""):
    user = auth.user_for_token(token)
    if not user:
        await ws.close(code=4401)
        return
    await ws.accept()
    hub.sockets[user] = ws
    gid = hub.player_game.get(user)
    if gid:
        await hub.send(user, hub.games[gid].state())
        await hub.presence(hub.games[gid])
    try:
        while True:
            msg = await ws.receive_json()
            if isinstance(msg, dict):
                await hub.handle(user, msg)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await hub.disconnect(user, ws)


FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
