from __future__ import annotations

import hashlib
import hmac
import json
import os
import random
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

OFFLINE_CAP_SECONDS = 12 * 60 * 60
DB_PATH = Path("game.db")
STAGES = {"employment": 1.0, "cabinet": 1.2, "studio": 1.5}

SKILLS = {
    "speed": {"base_cost": 100, "income_bonus": 0.02},
    "accuracy": {"base_cost": 140, "income_bonus": 0.0125},
    "communication": {"base_cost": 120, "income_bonus": 0.015},
    "hygiene": {"base_cost": 160, "income_bonus": 0.01},
    "marketing": {"base_cost": 200, "income_bonus": 0.02},
}

EVENTS = [
    {
        "id": "allergy_case",
        "text": "Клиент сообщает о возможной аллергии на металл. Ваше действие?",
        "answers": [
            "Предложить гипоаллергенный титан и проверить анкету.",
            "Игнорировать и сделать стандартный прокол.",
            "Сразу отменить запись без объяснений.",
        ],
        "correct": 0,
        "reward_money": 220,
        "reward_rep": 35,
        "buff_multiplier": 1.15,
        "buff_seconds": 120,
    },
    {
        "id": "inflammation_case",
        "text": "Клиент пришел с воспалением после другого мастера.",
        "answers": [
            "Дать медицинский диагноз и лечить на месте.",
            "Отказать в проколе и посоветовать обратиться к врачу.",
            "Сделать прокол поверх воспаления.",
        ],
        "correct": 1,
        "reward_money": 180,
        "reward_rep": 45,
        "buff_multiplier": 1.1,
        "buff_seconds": 150,
    },
    {
        "id": "sterilization",
        "text": "Перед сеансом вы замечаете, что журнал стерилизации не заполнен.",
        "answers": [
            "Заполнить позже, чтобы не задерживать клиента.",
            "Остановить прием, завершить протокол и только потом начать.",
            "Попросить коллегу поставить подпись без проверки.",
        ],
        "correct": 1,
        "reward_money": 250,
        "reward_rep": 50,
        "buff_multiplier": 1.2,
        "buff_seconds": 90,
    },
]


class AuthRequest(BaseModel):
    init_data: str


class SyncRequest(BaseModel):
    user_id: int


class UpgradeRequest(BaseModel):
    user_id: int
    skill: str


class ResolveEventRequest(BaseModel):
    user_id: int
    event_id: str
    answer_index: int


@dataclass
class UserState:
    money: float
    reputation: int
    stage: str
    last_seen_at: int
    buff_until: int
    buff_multiplier: float


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            tg_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            money REAL NOT NULL DEFAULT 0,
            reputation INTEGER NOT NULL DEFAULT 0,
            stage TEXT NOT NULL DEFAULT 'employment',
            last_seen_at INTEGER NOT NULL,
            buff_until INTEGER NOT NULL DEFAULT 0,
            buff_multiplier REAL NOT NULL DEFAULT 1.0
        );

        CREATE TABLE IF NOT EXISTS user_skills (
            user_id INTEGER NOT NULL,
            skill TEXT NOT NULL,
            level INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, skill)
        );

        CREATE TABLE IF NOT EXISTS user_event_log (
            user_id INTEGER NOT NULL,
            event_id TEXT NOT NULL,
            resolved_at INTEGER NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()


def parse_tg_init_data(init_data: str) -> dict[str, Any]:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "dev-token")
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    incoming_hash = parsed.pop("hash", "")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()

    if token != "dev-token" and incoming_hash != computed_hash:
        raise HTTPException(status_code=401, detail="Invalid Telegram signature")

    user_data = json.loads(parsed.get("user", "{}"))
    if not user_data:
        raise HTTPException(status_code=400, detail="No Telegram user payload")
    return user_data


def get_skill_levels(conn: sqlite3.Connection, user_id: int) -> dict[str, int]:
    rows = conn.execute("SELECT skill, level FROM user_skills WHERE user_id = ?", (user_id,)).fetchall()
    levels = {row["skill"]: row["level"] for row in rows}
    for skill_name in SKILLS:
        levels.setdefault(skill_name, 0)
    return levels


def income_per_sec(stage: str, levels: dict[str, int], buff_multiplier: float) -> float:
    base_income = 5.0
    skill_multiplier = 1.0 + sum(SKILLS[s]["income_bonus"] * lvl for s, lvl in levels.items())
    room_multiplier = STAGES.get(stage, 1.0)
    return round(base_income * skill_multiplier * room_multiplier * buff_multiplier, 3)


def ensure_user(conn: sqlite3.Connection, tg_id: int, username: str) -> int:
    now = int(time.time())
    row = conn.execute("SELECT id FROM users WHERE tg_id = ?", (tg_id,)).fetchone()
    if row:
        return row["id"]

    conn.execute(
        "INSERT INTO users (tg_id, username, money, reputation, stage, last_seen_at) VALUES (?, ?, 0, 0, 'employment', ?)",
        (tg_id, username, now),
    )
    user_id = conn.execute("SELECT id FROM users WHERE tg_id = ?", (tg_id,)).fetchone()["id"]
    conn.executemany(
        "INSERT INTO user_skills (user_id, skill, level) VALUES (?, ?, 0)",
        [(user_id, skill_name) for skill_name in SKILLS],
    )
    conn.commit()
    return user_id


def load_user_state(conn: sqlite3.Connection, user_id: int) -> UserState:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return UserState(
        money=row["money"],
        reputation=row["reputation"],
        stage=row["stage"],
        last_seen_at=row["last_seen_at"],
        buff_until=row["buff_until"],
        buff_multiplier=row["buff_multiplier"],
    )


def apply_offline_progress(conn: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    now = int(time.time())
    state = load_user_state(conn, user_id)
    levels = get_skill_levels(conn, user_id)

    active_buff = state.buff_multiplier if now < state.buff_until else 1.0
    offline_delta = max(0, now - state.last_seen_at)
    effective_delta = min(offline_delta, OFFLINE_CAP_SECONDS)
    earned = income_per_sec(state.stage, levels, active_buff) * effective_delta
    new_money = state.money + earned

    conn.execute(
        "UPDATE users SET money = ?, last_seen_at = ?, buff_multiplier = ?, buff_until = ? WHERE id = ?",
        (new_money, now, active_buff, state.buff_until if active_buff > 1 else 0, user_id),
    )
    conn.commit()

    return {
        "money": round(new_money, 2),
        "reputation": state.reputation,
        "stage": state.stage,
        "skills": levels,
        "income_per_sec": income_per_sec(state.stage, levels, active_buff),
        "offline_seconds": effective_delta,
        "offline_earned": round(earned, 2),
        "next_event": random.choice(EVENTS),
    }


def upgrade_cost(skill: str, level: int) -> int:
    return int(SKILLS[skill]["base_cost"] * (1.15**level))


app = FastAPI(title="Piercing Tycoon API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_headers=["*"], allow_methods=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/")
def root() -> FileResponse:
    return FileResponse("static/index.html")


@app.post("/auth")
def auth(req: AuthRequest) -> dict[str, Any]:
    user_payload = parse_tg_init_data(req.init_data)
    tg_id = int(user_payload["id"])
    username = user_payload.get("username", f"user_{tg_id}")

    conn = get_conn()
    user_id = ensure_user(conn, tg_id, username)
    snapshot = apply_offline_progress(conn, user_id)
    conn.close()
    return {"user_id": user_id, "username": username, **snapshot}


@app.post("/sync")
def sync(req: SyncRequest) -> dict[str, Any]:
    conn = get_conn()
    snapshot = apply_offline_progress(conn, req.user_id)
    conn.close()
    return snapshot


@app.post("/upgrade")
def upgrade(req: UpgradeRequest) -> dict[str, Any]:
    if req.skill not in SKILLS:
        raise HTTPException(status_code=400, detail="Unknown skill")

    conn = get_conn()
    state = load_user_state(conn, req.user_id)
    levels = get_skill_levels(conn, req.user_id)
    level = levels[req.skill]
    cost = upgrade_cost(req.skill, level)

    if state.money < cost:
        raise HTTPException(status_code=400, detail="Not enough money")

    new_money = state.money - cost
    conn.execute("UPDATE users SET money = ? WHERE id = ?", (new_money, req.user_id))
    conn.execute("UPDATE user_skills SET level = level + 1 WHERE user_id = ? AND skill = ?", (req.user_id, req.skill))

    new_levels = get_skill_levels(conn, req.user_id)
    rep_gain = 3
    conn.execute("UPDATE users SET reputation = reputation + ? WHERE id = ?", (rep_gain, req.user_id))

    if state.stage == "employment" and new_levels["speed"] >= 5 and state.reputation + rep_gain >= 40:
        conn.execute("UPDATE users SET stage = 'cabinet' WHERE id = ?", (req.user_id,))

    conn.commit()
    updated = load_user_state(conn, req.user_id)
    conn.close()

    return {
        "money": round(new_money, 2),
        "skills": new_levels,
        "reputation": updated.reputation,
        "stage": updated.stage,
        "income_per_sec": income_per_sec(updated.stage, new_levels, updated.buff_multiplier),
    }


@app.post("/event/resolve")
def resolve_event(req: ResolveEventRequest) -> dict[str, Any]:
    event = next((e for e in EVENTS if e["id"] == req.event_id), None)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    conn = get_conn()
    state = load_user_state(conn, req.user_id)

    if req.answer_index == event["correct"]:
        money_delta = event["reward_money"]
        rep_delta = event["reward_rep"]
        buff_multiplier = event["buff_multiplier"]
        buff_until = int(time.time()) + event["buff_seconds"]
        is_correct = True
    else:
        money_delta = -120
        rep_delta = -30
        buff_multiplier = 1.0
        buff_until = 0
        is_correct = False

    new_money = max(0.0, state.money + money_delta)
    conn.execute(
        "UPDATE users SET money = ?, reputation = reputation + ?, buff_multiplier = ?, buff_until = ? WHERE id = ?",
        (new_money, rep_delta, buff_multiplier, buff_until, req.user_id),
    )
    conn.execute(
        "INSERT INTO user_event_log (user_id, event_id, resolved_at) VALUES (?, ?, ?)",
        (req.user_id, req.event_id, int(time.time())),
    )
    conn.commit()

    updated = load_user_state(conn, req.user_id)
    levels = get_skill_levels(conn, req.user_id)
    conn.close()

    return {
        "correct": is_correct,
        "money": round(updated.money, 2),
        "reputation": updated.reputation,
        "buff_until": updated.buff_until,
        "income_per_sec": income_per_sec(updated.stage, levels, updated.buff_multiplier),
    }


@app.get("/leaderboard")
def leaderboard() -> dict[str, Any]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT username, reputation, stage FROM users ORDER BY reputation DESC, money DESC LIMIT 100"
    ).fetchall()
    conn.close()
    return {
        "items": [
            {"rank": idx + 1, "username": row["username"], "reputation": row["reputation"], "stage": row["stage"]}
            for idx, row in enumerate(rows)
        ]
    }
