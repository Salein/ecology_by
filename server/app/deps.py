from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.services.auth_users import UserRecord, get_user_by_id

security = HTTPBearer(auto_error=False)


def _decode_token(token: str) -> dict:
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=["HS256"],
        options={"require": ["exp", "sub"]},
    )


def create_access_token(user: UserRecord) -> str:
    import time

    exp = int(time.time()) + settings.jwt_expire_hours * 3600
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "exp": exp,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _session_cookie_secure() -> bool:
    """SameSite=None требует Secure; иначе браузер отбросит cookie."""
    return settings.auth_cookie_secure or settings.auth_cookie_samesite == "none"


def attach_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        httponly=True,
        max_age=settings.jwt_expire_hours * 3600,
        samesite=settings.auth_cookie_samesite,
        path="/",
        secure=_session_cookie_secure(),
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        settings.auth_cookie_name,
        path="/",
        secure=_session_cookie_secure(),
        httponly=True,
        samesite=settings.auth_cookie_samesite,
    )


async def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(security),
) -> UserRecord:
    token: str | None = None
    if creds is not None and creds.scheme.lower() == "bearer":
        token = creds.credentials
    if not token:
        token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        data = _decode_token(token)
        uid = int(data["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный или просроченный токен",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    user = get_user_by_id(uid)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден")
    if user.blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ к сервису заблокирован",
        )
    return user


async def require_admin(user: Annotated[UserRecord, Depends(get_current_user)]) -> UserRecord:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нужны права администратора")
    return user
