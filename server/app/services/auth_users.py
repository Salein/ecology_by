from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import bcrypt
from sqlalchemy import select

from app.config import settings
from app.db.models import UserModel
from app.db.session import session_scope

_DATA = Path(__file__).resolve().parent.parent / "data"
USERS_PATH = _DATA / "auth_users.json"

Role = Literal["user", "admin"]
_LAST_SEEN_TOUCH_INTERVAL = timedelta(minutes=5)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class UserRecord:
    id: int
    email: str
    name: str
    password_hash: str
    role: Role
    created_at: str
    last_seen_at: str | None = None
    blocked: bool = False
    subscription_active: bool = False

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "role": self.role,
            "created_at": self.created_at,
            "last_seen_at": self.last_seen_at,
            "blocked": self.blocked,
            "subscription_active": self.subscription_active,
        }


def _model_to_record(model: UserModel) -> UserRecord:
    role = model.role if model.role in ("user", "admin") else "user"
    return UserRecord(
        id=int(model.id),
        email=str(model.email),
        name=str(model.name or ""),
        password_hash=str(model.password_hash),
        role=role,  # type: ignore[arg-type]
        created_at=str(model.created_at or ""),
        last_seen_at=str(model.last_seen_at).strip() if model.last_seen_at else None,
        blocked=bool(model.blocked),
        subscription_active=bool(model.subscription_active),
    )


def is_bootstrap_owner_user(user: UserRecord) -> bool:
    owner_em = (settings.bootstrap_owner_email or "").strip().casefold()
    if not owner_em:
        return False
    return user.email.strip().casefold() == owner_em


def list_users() -> list[UserRecord]:
    with session_scope() as session:
        rows = session.execute(select(UserModel).order_by(UserModel.id.asc())).scalars().all()
        return [_model_to_record(row) for row in rows]


def get_user_by_id(uid: int) -> UserRecord | None:
    with session_scope() as session:
        row = session.get(UserModel, uid)
        return _model_to_record(row) if row else None


def get_user_by_email(email: str) -> UserRecord | None:
    key = email.strip().casefold()
    with session_scope() as session:
        row = session.execute(select(UserModel).where(UserModel.email.ilike(key))).scalars().first()
        return _model_to_record(row) if row else None


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


def touch_user_last_seen(user_id: int, *, force: bool = False) -> None:
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    with session_scope() as session:
        row = session.get(UserModel, user_id)
        if not row:
            return
        if not force and row.last_seen_at:
            try:
                prev = datetime.fromisoformat(str(row.last_seen_at).replace("Z", "+00:00"))
                if prev.tzinfo is None:
                    prev = prev.replace(tzinfo=timezone.utc)
                if now - prev < _LAST_SEEN_TOUCH_INTERVAL:
                    return
            except (ValueError, TypeError, OverflowError):
                pass
        row.last_seen_at = now_iso
        session.add(row)


def register_user(email: str, password: str, name: str) -> UserRecord:
    email_n = email.strip().lower()
    if len(password) < 8:
        raise ValueError("Пароль не короче 8 символов.")
    name_s = " ".join((name or "").replace("\xa0", " ").split()).strip() or email_n.split("@")[0]

    with session_scope() as session:
        existing = session.execute(select(UserModel).where(UserModel.email == email_n)).scalars().first()
        if existing:
            raise ValueError("Пользователь с такой почтой уже зарегистрирован.")
        users_count = session.query(UserModel).count()
        role: Role = "admin" if users_count == 0 else "user"
        created = _utc_iso()
        row = UserModel(
            email=email_n,
            name=name_s,
            password_hash=hash_password(password),
            role=role,
            created_at=created,
            last_seen_at=created,
            blocked=False,
            subscription_active=True,
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _model_to_record(row)


def ensure_bootstrap_owner_account(email: str, password: str) -> None:
    email_n = (email or "").strip().lower()
    if not email_n or len(password) < 8:
        return
    ph = hash_password(password)

    with session_scope() as session:
        row = session.execute(select(UserModel).where(UserModel.email == email_n)).scalars().first()
        if row:
            row.password_hash = ph
            row.role = "admin"
            row.blocked = False
            row.subscription_active = True
            session.add(row)
            return

        created = _utc_iso()
        name_s = email_n.split("@")[0] or "Admin"
        row = UserModel(
            email=email_n,
            name=name_s,
            password_hash=ph,
            role="admin",
            created_at=created,
            last_seen_at=created,
            blocked=False,
            subscription_active=True,
        )
        session.add(row)


def update_user_admin(
    user_id: int,
    *,
    role: Role | None = None,
    blocked: bool | None = None,
    subscription_active: bool | None = None,
) -> UserRecord | None:
    if role is None and blocked is None and subscription_active is None:
        return None

    with session_scope() as session:
        row = session.get(UserModel, user_id)
        if not row:
            return None
        rec_check = _model_to_record(row)
        if is_bootstrap_owner_user(rec_check):
            row.role = "admin"
        elif role is not None:
            row.role = role

        rec_check = _model_to_record(row)
        if is_bootstrap_owner_user(rec_check):
            row.blocked = False
            row.subscription_active = True
        elif subscription_active is not None:
            row.subscription_active = bool(subscription_active)
            row.blocked = not bool(subscription_active)
        elif blocked is not None:
            row.blocked = bool(blocked)
            row.subscription_active = not bool(blocked)
        else:
            row.subscription_active = not bool(row.blocked)
        session.add(row)
        session.flush()
        session.refresh(row)
        return _model_to_record(row)


def delete_user(user_id: int) -> bool:
    with session_scope() as session:
        row = session.get(UserModel, user_id)
        if not row:
            return False
        target = _model_to_record(row)
        if is_bootstrap_owner_user(target):
            raise ValueError("Нельзя удалить учётную запись владельца системы")
        admins_count = session.query(UserModel).filter(UserModel.role == "admin").count()
        if target.role == "admin" and admins_count <= 1:
            raise ValueError("Нельзя удалить единственного администратора")
        session.delete(row)
        return True


def import_users_from_json(path: Path = USERS_PATH) -> int:
    if not path.is_file():
        return 0
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    users = data.get("users") if isinstance(data, dict) else None
    if not isinstance(users, list):
        return 0

    imported = 0
    with session_scope() as session:
        for raw in users:
            if not isinstance(raw, dict):
                continue
            raw_id = _safe_int(raw.get("id"))
            email = str(raw.get("email") or "").strip().lower()
            ph = str(raw.get("password_hash") or "").strip()
            if not email or not ph:
                continue
            role = str(raw.get("role") or "user")
            if role not in ("user", "admin"):
                role = "user"
            blocked = bool(raw.get("blocked", False))
            rec = session.execute(select(UserModel).where(UserModel.email == email)).scalars().first()
            if not rec:
                rec = UserModel(
                    id=raw_id if raw_id is not None else None,  # type: ignore[arg-type]
                    email=email,
                    password_hash=ph,
                    name=str(raw.get("name") or ""),
                )
            rec.name = str(raw.get("name") or "")
            rec.password_hash = ph
            rec.role = role
            rec.created_at = str(raw.get("created_at") or _utc_iso())
            rec.last_seen_at = str(raw.get("last_seen_at")).strip() if raw.get("last_seen_at") else None
            rec.blocked = blocked
            rec.subscription_active = not blocked
            session.add(rec)
            imported += 1
    return imported
