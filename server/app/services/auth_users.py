from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import bcrypt

from app.config import settings

_DATA = Path(__file__).resolve().parent.parent / "data"
USERS_PATH = _DATA / "auth_users.json"

Role = Literal["user", "admin"]


def is_bootstrap_owner_user(user: UserRecord) -> bool:
    """Почта из BOOTSTRAP_OWNER_EMAIL — учётная запись создателя/владельца, её нельзя удалить."""
    owner_em = (settings.bootstrap_owner_email or "").strip().casefold()
    if not owner_em:
        return False
    return user.email.strip().casefold() == owner_em


@dataclass
class UserRecord:
    id: int
    email: str
    name: str
    password_hash: str
    role: Role
    created_at: str
    blocked: bool = False

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "role": self.role,
            "created_at": self.created_at,
            "blocked": self.blocked,
        }


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_store() -> dict[str, Any]:
    if not USERS_PATH.is_file():
        return {"next_id": 1, "users": []}
    with open(USERS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {"next_id": 1, "users": []}
    data.setdefault("next_id", 1)
    data.setdefault("users", [])
    return data


def _save_store(data: dict[str, Any]) -> None:
    _DATA.mkdir(parents=True, exist_ok=True)
    tmp = USERS_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(USERS_PATH)


def _row_to_record(row: dict[str, Any]) -> UserRecord:
    role = row.get("role") or "user"
    if role not in ("user", "admin"):
        role = "user"
    blocked = bool(row.get("blocked", False))
    return UserRecord(
        id=int(row["id"]),
        email=str(row["email"]),
        name=str(row.get("name") or ""),
        password_hash=str(row["password_hash"]),
        role=role,  # type: ignore[arg-type]
        created_at=str(row.get("created_at") or ""),
        blocked=blocked,
    )


def list_users() -> list[UserRecord]:
    data = _load_store()
    users = data.get("users") or []
    if not isinstance(users, list):
        return []
    out: list[UserRecord] = []
    for row in users:
        if isinstance(row, dict) and "id" in row and "email" in row and "password_hash" in row:
            try:
                out.append(_row_to_record(row))
            except (KeyError, TypeError, ValueError):
                continue
    return out


def get_user_by_id(uid: int) -> UserRecord | None:
    for u in list_users():
        if u.id == uid:
            return u
    return None


def get_user_by_email(email: str) -> UserRecord | None:
    key = email.strip().casefold()
    for u in list_users():
        if u.email.casefold() == key:
            return u
    return None


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


def register_user(email: str, password: str, name: str) -> UserRecord:
    email_n = email.strip().lower()
    if get_user_by_email(email_n):
        raise ValueError("Пользователь с такой почтой уже зарегистрирован.")
    if len(password) < 8:
        raise ValueError("Пароль не короче 8 символов.")
    name_s = " ".join((name or "").replace("\xa0", " ").split()).strip() or email_n.split("@")[0]

    data = _load_store()
    users: list[dict[str, Any]] = list(data.get("users") or [])
    next_id = int(data.get("next_id") or 1)
    # первый зарегистрированный пользователь — администратор
    role: Role = "admin" if not users else "user"
    rec = {
        "id": next_id,
        "email": email_n,
        "name": name_s,
        "password_hash": hash_password(password),
        "role": role,
        "created_at": _utc_iso(),
        "blocked": False,
    }
    users.append(rec)
    data["users"] = users
    data["next_id"] = next_id + 1
    _save_store(data)
    return _row_to_record(rec)


def ensure_bootstrap_owner_account(email: str, password: str) -> None:
    """
    Создаёт или обновляет указанного пользователя: роль admin, пароль из bootstrap.
    Вызывается при старте приложения.
    """
    email_n = (email or "").strip().lower()
    if not email_n or len(password) < 8:
        return
    ph = hash_password(password)
    existing = get_user_by_email(email_n)
    data = _load_store()
    users: list[dict[str, Any]] = list(data.get("users") or [])

    if existing:
        for i, row in enumerate(users):
            if not isinstance(row, dict):
                continue
            if str(row.get("email", "")).strip().lower() != email_n:
                continue
            row["password_hash"] = ph
            row["role"] = "admin"
            row["blocked"] = False
            users[i] = row
            data["users"] = users
            _save_store(data)
            return

    next_id = int(data.get("next_id") or 1)
    name_s = email_n.split("@")[0] or "Admin"
    rec = {
        "id": next_id,
        "email": email_n,
        "name": name_s,
        "password_hash": ph,
        "role": "admin",
        "created_at": _utc_iso(),
        "blocked": False,
    }
    users.append(rec)
    data["users"] = users
    data["next_id"] = next_id + 1
    _save_store(data)


def update_user_admin(
    user_id: int,
    *,
    role: Role | None = None,
    blocked: bool | None = None,
) -> UserRecord | None:
    if role is None and blocked is None:
        return None
    data = _load_store()
    users = data.get("users") or []
    if not isinstance(users, list):
        return None
    for i, row in enumerate(users):
        if not isinstance(row, dict):
            continue
        if int(row.get("id", -1)) != user_id:
            continue
        if role is not None:
            row["role"] = role
        if blocked is not None:
            row["blocked"] = blocked
        users[i] = row
        data["users"] = users
        _save_store(data)
        return _row_to_record(row)
    return None


def delete_user(user_id: int) -> bool:
    """
    Удаляет пользователя из хранилища.
    Выбрасывает ValueError, если это единственный администратор.
    Возвращает False, если пользователь не найден.
    """
    users_list = list_users()
    target = get_user_by_id(user_id)
    if not target:
        return False
    if is_bootstrap_owner_user(target):
        raise ValueError("Нельзя удалить учётную запись владельца системы")
    admins = [u for u in users_list if u.role == "admin"]
    if target.role == "admin" and len(admins) <= 1:
        raise ValueError("Нельзя удалить единственного администратора")

    data = _load_store()
    raw = data.get("users") or []
    if not isinstance(raw, list):
        return False
    new_users: list[dict[str, Any]] = []
    removed = False
    for row in raw:
        if not isinstance(row, dict):
            continue
        try:
            rid = int(row.get("id", -1))
        except (TypeError, ValueError):
            new_users.append(row)
            continue
        if rid == user_id:
            removed = True
            continue
        new_users.append(row)
    if not removed:
        return False
    data["users"] = new_users
    _save_store(data)
    return True
