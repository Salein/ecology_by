from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.deps import attach_session_cookie, clear_session_cookie, create_access_token, get_current_user
from app.schemas import AuthSessionResponse, LoginRequest, RegisterRequest, UserOut
from app.services.auth_users import (
    UserRecord,
    get_user_by_email,
    is_bootstrap_owner_user,
    register_user,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_user_out(u: UserRecord) -> UserOut:
    return UserOut(
        id=u.id,
        email=u.email,
        name=u.name,
        role=u.role,
        created_at=u.created_at,
        blocked=u.blocked,
        protected_account=is_bootstrap_owner_user(u),
    )


@router.post("/register", response_model=AuthSessionResponse)
async def register(body: RegisterRequest, response: Response) -> AuthSessionResponse:
    try:
        user = register_user(body.email, body.password, body.name)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    token = create_access_token(user)
    attach_session_cookie(response, token)
    return AuthSessionResponse(user=_to_user_out(user))


@router.post("/login", response_model=AuthSessionResponse)
async def login(body: LoginRequest, response: Response) -> AuthSessionResponse:
    user = get_user_by_email(str(body.email))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверная почта или пароль",
        )
    if user.blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ к сервису заблокирован",
        )
    token = create_access_token(user)
    attach_session_cookie(response, token)
    return AuthSessionResponse(user=_to_user_out(user))


@router.post("/logout")
async def logout(response: Response) -> dict:
    """Сбрасывает cookie сессии (можно вызывать без валидного токена)."""
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user: UserRecord = Depends(get_current_user)) -> UserOut:
    return _to_user_out(user)
