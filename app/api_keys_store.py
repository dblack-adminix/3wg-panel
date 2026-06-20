import hashlib
import re
import secrets
import sqlite3
import time
from pathlib import Path


def token_hash(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def token_mask(token: str) -> tuple[str, str]:
    token = str(token)
    return token[:6], token[-4:]


def connect(db_path: Path | str):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_api_keys(db_path: Path | str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                token_prefix TEXT NOT NULL DEFAULT '',
                token_suffix TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                last_used_at INTEGER
            )
            """
        )
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(api_keys)").fetchall()]
        if "token" in cols:
            rows = conn.execute("SELECT id, name, token, created_at, last_used_at FROM api_keys ORDER BY id").fetchall()
            conn.execute(
                """
                CREATE TABLE api_keys_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    token_prefix TEXT NOT NULL DEFAULT '',
                    token_suffix TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    last_used_at INTEGER
                )
                """
            )
            for row in rows:
                prefix, suffix = token_mask(row["token"])
                conn.execute(
                    """
                    INSERT OR IGNORE INTO api_keys_new
                    (id, name, token_hash, token_prefix, token_suffix, created_at, last_used_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(row["id"]),
                        row["name"],
                        token_hash(row["token"]),
                        prefix,
                        suffix,
                        int(row["created_at"]),
                        int(row["last_used_at"]) if row["last_used_at"] else None,
                    ),
                )
            conn.execute("DROP TABLE api_keys")
            conn.execute("ALTER TABLE api_keys_new RENAME TO api_keys")
        else:
            cols = [r["name"] for r in conn.execute("PRAGMA table_info(api_keys)").fetchall()]
            if "token_prefix" not in cols:
                conn.execute("ALTER TABLE api_keys ADD COLUMN token_prefix TEXT NOT NULL DEFAULT ''")
            if "token_suffix" not in cols:
                conn.execute("ALTER TABLE api_keys ADD COLUMN token_suffix TEXT NOT NULL DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_token_hash ON api_keys(token_hash)")
        conn.commit()


def valid_api_key(db_path: Path | str, token: str) -> bool:
    hashed = token_hash(token)
    with connect(db_path) as conn:
        row = conn.execute("SELECT id, token_hash FROM api_keys WHERE token_hash = ?", (hashed,)).fetchone()
        if row and secrets.compare_digest(str(row["token_hash"]), hashed):
            conn.execute("UPDATE api_keys SET last_used_at = ? WHERE id = ?", (int(time.time()), row["id"]))
            conn.commit()
            return True
    return False


def list_api_keys(db_path: Path | str) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, name, token_prefix, token_suffix, created_at, last_used_at FROM api_keys ORDER BY id DESC"
        ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "name": row["name"],
            "token_masked": f"{row['token_prefix']}...{row['token_suffix']}",
            "created_at": int(row["created_at"]),
            "last_used_at": int(row["last_used_at"]) if row["last_used_at"] else None,
        }
        for row in rows
    ]


def create_api_key(db_path: Path | str, name: str) -> dict:
    clean_name = re.sub(r"\s+", " ", str(name or "").strip())[:80] or "integration"
    token = secrets.token_urlsafe(32)
    prefix, suffix = token_mask(token)
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO api_keys(name, token_hash, token_prefix, token_suffix, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (clean_name, token_hash(token), prefix, suffix, int(time.time())),
        )
        conn.commit()
        key_id = int(cur.lastrowid)
    return {"id": key_id, "name": clean_name, "token": token}


def delete_api_key(db_path: Path | str, key_id: int) -> bool:
    with connect(db_path) as conn:
        cur = conn.execute("DELETE FROM api_keys WHERE id = ?", (int(key_id),))
        conn.commit()
        return cur.rowcount > 0
