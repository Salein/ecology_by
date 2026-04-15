from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import require_admin
from app.schemas import UserAdminUpdate, UserOut
from app.services.auth_users import (
    UserRecord,
    delete_user,
    get_user_by_id,
    is_bootstrap_owner_user,
    list_users,
    update_user_admin,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[UserOut])
async def admin_list_users(_: Annotated[UserRecord, Depends(require_admin)]) -> list[UserOut]:
    return [
        UserOut(
            id=u.id,
            email=u.email,
            name=u.name,
            role=u.role,
            created_at=u.created_at,
            last_seen_at=u.last_seen_at,
            blocked=u.blocked,
            subscription_active=u.subscription_active,
            protected_account=is_bootstrap_owner_user(u),
        )
        for u in list_users()
    ]


@router.patch("/users/{user_id}", response_model=UserOut)
async def admin_update_user(
    user_id: int,
    body: UserAdminUpdate,
    admin: Annotated[UserRecord, Depends(require_admin)],
) -> UserOut:
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    if is_bootstrap_owner_user(target) and body.blocked is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя изменять доступ к сервису для учётной записи владельца системы",
        )
    if is_bootstrap_owner_user(target) and body.role is not None and body.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Роль учётной записи владельца системы всегда администратор",
        )
    if body.blocked is True and user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя заблокировать свою учётную запись",
        )
    if body.subscription_active is False and user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя отключить подписку и доступ к своей учётной записи",
        )
    updated = update_user_admin(
        user_id,
        role=body.role,
        blocked=body.blocked,
        subscription_active=body.subscription_active,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    return UserOut(
        id=updated.id,
        email=updated.email,
        name=updated.name,
        role=updated.role,
        created_at=updated.created_at,
        last_seen_at=updated.last_seen_at,
        blocked=updated.blocked,
        subscription_active=updated.subscription_active,
        protected_account=is_bootstrap_owner_user(updated),
    )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_user(
    user_id: int,
    admin: Annotated[UserRecord, Depends(require_admin)],
) -> None:
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя удалить свою учётную запись",
        )
    try:
        ok = delete_user(user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
