from typing import Literal, Self

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class ObjectSearchRequest(BaseModel):
    query: str = ""
    waste_code: str | None = None
    lat: float | None = None
    lon: float | None = None

    @field_validator("lat", "lon", mode="before")
    @classmethod
    def coerce_lat_lon(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip()
            return float(s) if s else None
        return v


class WasteObjectOut(BaseModel):
    id: int
    owner: str
    object_name: str
    address: str | None = None
    phones: str | None = None
    waste_code: str | None = None
    waste_type_name: str | None = None
    accepts_external_waste: bool = True
    # Для обратной совместимости: "основная" дистанция (по дорогам, если есть, иначе по воздуху)
    distance_km: float | None = None
    # Явные поля двух методов расчёта
    distance_air_km: float | None = None
    distance_road_km: float | None = None
    # Причина, если маршрут по дорогам не удалось посчитать
    distance_road_error: str | None = None
    # Все дистанции в выдаче являются оценочными; spread — ориентировочный разброс (± км).
    distance_is_approx: bool = True
    distance_spread_km: float | None = None
    distance_spread_note: str | None = None
    distance_note: str | None = None


class ObjectSearchResponse(BaseModel):
    items: list[WasteObjectOut]


class PdfExtractResponse(BaseModel):
    pages: int
    text: str
    tables_preview: list[list[list[str | None]]] = Field(default_factory=list)


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    role: Literal["user", "admin"]
    created_at: str
    last_seen_at: str | None = None
    blocked: bool = False
    subscription_active: bool = Field(
        default=False,
        description="Активная подписка (в т.ч. выставлена администратором вручную)",
    )
    protected_account: bool = Field(
        default=False,
        description="Учётная запись из BOOTSTRAP_OWNER_EMAIL — удаление недоступно",
    )


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def validate_name_not_blank(cls, v: str) -> str:
        s = " ".join(v.replace("\xa0", " ").split()).strip()
        if not s:
            raise ValueError("Имя обязательно")
        return s


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class AuthSessionResponse(BaseModel):
    """Только профиль; JWT в HttpOnly cookie (Set-Cookie), не в теле ответа."""

    user: UserOut


class UserAdminUpdate(BaseModel):
    """Хотя бы одно поле; частичное обновление роли, блокировки и/или подписки."""

    role: Literal["user", "admin"] | None = None
    blocked: bool | None = None
    subscription_active: bool | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> Self:
        if self.role is None and self.blocked is None and self.subscription_active is None:
            raise ValueError("Укажите role, blocked и/или subscription_active")
        return self
