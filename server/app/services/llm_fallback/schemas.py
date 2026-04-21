from __future__ import annotations

from pydantic import BaseModel


class LlmWasteRecord(BaseModel):
    waste_code: str | None = None
    waste_name: str | None = None
    object_name: str | None = None
    owner_name: str | None = None
    user_address: str | None = None
    user_phone: str | None = None
    object_id: int | None = None
    owner_address: str | None = None
    owner_phone: str | None = None
    accepts_from_others: bool | None = None


class LlmExtractionBatch(BaseModel):
    records: list[LlmWasteRecord]
