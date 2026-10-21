import hashlib
import hmac
import os
import re
import secrets
import sqlite3

DB_PATH = os.environ.get("CHESS_DB", "chess.db")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect() as c:
        c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL COLLATE NOCASE, salt BLOB NOT NULL, pw_hash BLOB NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, username TEXT NOT NULL)")


def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)


def create_user(username: str, password: str) -> bool:
    salt = os.urandom(16)
    try:
        with connect() as c:
            c.execute("INSERT INTO users (username, salt, pw_hash) VALUES (?,?,?)", (username, salt, _hash(password, salt)))
        return True
    except sqlite3.IntegrityError:
        return False


def verify_user(username: str, password: str):
    with connect() as c:
        row = c.execute("SELECT username, salt, pw_hash FROM users WHERE username=?", (username,)).fetchone()
    if row and hmac.compare_digest(row["pw_hash"], _hash(password, row["salt"])):
        return row["username"]
    return None


def create_session(username: str) -> str:
    token = secrets.token_urlsafe(32)
    with connect() as c:
        c.execute("INSERT INTO sessions (token, username) VALUES (?,?)", (token, username))
    return token


def user_for_token(token: str):
    with connect() as c:
        row = c.execute("SELECT username FROM sessions WHERE token=?", (token,)).fetchone()
    return row["username"] if row else None


def delete_session(token: str):
    with connect() as c:
        c.execute("DELETE FROM sessions WHERE token=?", (token,))
