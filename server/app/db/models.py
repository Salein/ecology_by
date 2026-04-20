from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="user", index=True)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    last_seen_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    subscription_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class RegistryCacheMetaModel(Base):
    __tablename__ = "registry_cache_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, default=1)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)
    source_signature: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sources: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # [{sha256, part, name}, ...] — для слияния частей I/II при отдельных POST и для skip по набору файлов
    import_sources_detail: Mapped[list | None] = mapped_column(JSON, nullable=True)


class RegistryRecordModel(Base):
    __tablename__ = "registry_records"

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_part: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    record_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    owner: Mapped[str] = mapped_column(Text, nullable=False, default="")
    object_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    waste_code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    waste_type_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    accepts_external_waste: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    phones: Mapped[str | None] = mapped_column(Text, nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_registry_records_record_id_waste_code", "record_id", "waste_code"),
        Index("ix_registry_records_accepts_external_waste", "accepts_external_waste"),
        Index("ix_registry_records_source_part_record_id", "source_part", "record_id"),
    )


class GeocodeCacheModel(Base):
    __tablename__ = "geocode_cache"

    key: Mapped[str] = mapped_column(String(280), primary_key=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
