from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import settings

logger = logging.getLogger(__name__)
LLM_FEATURE_ENABLED = False

REPAIR_ADDRESS_SYSTEM_PROMPT = (
    "Ты — repair-модуль для адресов объектов реестра отходов (Беларусь). "
    "На входе JSON candidates: id, waste_code, address, owner, object_name (для контекста). "
    "Верни ТОЛЬКО валидный JSON формата {\"records\": [...]} с той же схемой полей, что и extractor. "
    "Задача: исправить поле address — добавь недостающий населённый пункт или улицу, если они явно следуют из индекса/области; "
    "не выдумывай улицу без оснований в тексте. Если адрес уже полный — верни его с лёгкой нормализацией пробелов. "
    "Сохрани id и waste_code без изменений. phones/owner можно вернуть как во входе. "
    "Вывод: только JSON, без markdown."
)

REPAIR_FULL_SYSTEM_PROMPT = (
    "Ты — repair-модуль для записей реестра отходов (Беларусь). "
    "На входе JSON candidates: id, waste_code, owner, object_name, waste_type_name, address, phones, accepts_external_waste, source_part; "
    "опционально source_excerpt — сырой фрагмент текста PDF вокруг строки «Объект …» и соответствующего кода ФККО. "
    "Верни ТОЛЬКО валидный JSON {\"records\": [...]} по той же схеме (без поля source_excerpt в ответе). "
    "Исправь любые ошибки парсера: пустые/обрезанные owner, object_name, waste_type_name, phones, address; "
    "если в candidates поле пустое, а в source_excerpt оно явно видно — восстанови его из source_excerpt. "
    "Убери лишний шум в текстах (дубли, мусор из PDF), нормализуй адрес (индекс, область, НП, улица). "
    "Поле accepts_external_waste: true если объект принимает отходы от других лиц/организаций, false если только свои, "
    "null если по тексту нельзя надёжно решить (например, в PDF не видно колонки с чекбоксами). "
    "Не выдумывай телефоны и коды ФККО: waste_code только 7 цифр или null. "
    "Телефоны только из текста candidates и source_excerpt; не генерируй номера «с головы». "
    "Если во входной записи phones пустой, а в source_excerpt (или в той же строке карточки) виден телефон/факс — "
    "обязательно извлеки все такие номера в phones (массив строк): +375…, 80…, 8-0…, (0xx)…, 8-02xx…, «тел.» и т.п.; "
    "разные номера — отдельные элементы массива, без дублей. Если в excerpts номеров нет — оставь phones пустым. "
    "Номер может быть «рваным» из-за переносов PDF: например «(017)» на одной строке, продолжение цифр на следующих — "
    "если по соседним строкам очевидно один номер для этой же карточки (тот же объект/собственник), склей в одну строку в phones; "
    "не подмешивай номера из соседних карточек других объектов. Аналогично можно аккуратно склеить разорванный адрес или название, "
    "если фрагменты явно относятся к одной записи и видны в source_excerpt. "
    "Сохрани id и waste_code как во входе. Одна входная запись -> одна выходная. Вывод: только JSON, без markdown."
)

DEFAULT_SYSTEM_PROMPT = (
    "Ты — extractor структурированных данных из PDF реестров объектов по использованию отходов (Беларусь). "
    "Твоя задача: из входного текста PDF вернуть ТОЛЬКО валидный JSON по заданной схеме, без пояснений.\n\n"
    "Правила:\n"
    "1) Не выдумывай данные. Если поля нет или неуверен — ставь null.\n"
    "2) Не добавляй поля, которых нет в схеме.\n"
    "3) Для waste_code используй только 7 цифр. Иначе null.\n"
    "4) address верни как строку исходного адреса (без фантазии, но с аккуратной нормализацией пробелов).\n"
    "5) phones — массив строк телефонов в исходном виде, без дублей.\n"
    "6) accepts_external_waste: true/false только при явном признаке; если неясно — null.\n"
    "7) source_part = 1 или 2, если видно из контекста; иначе null.\n"
    "8) Для каждой записи дай confidence от 0 до 1.\n"
    "9) Верни JSON строго формата {\"records\": [...]}.\n"
    "Вывод: только JSON, без markdown, без комментариев, без префиксов."
)


class RegistryLlmRecord(BaseModel):
    id: int | None = None
    owner: str | None = None
    object_name: str | None = None
    waste_code: str | None = None
    waste_type_name: str | None = None
    accepts_external_waste: bool | None = None
    address: str | None = None
    phones: list[str] = Field(default_factory=list)
    source_part: int | None = None
    confidence: float = 0.0


class RegistryLlmResponse(BaseModel):
    records: list[RegistryLlmRecord] = Field(default_factory=list)


_OBJ_SPLIT_RE = re.compile(r"(?i)(?=Объект\s*(?:№\.?)?\s*\d+\b)")


def _strip_code_fence(s: str) -> str:
    text = (s or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _chunk_registry_text(text: str, chunk_chars: int, overlap_chars: int) -> list[str]:
    compact = (text or "").strip()
    if not compact:
        return []
    if len(compact) <= chunk_chars:
        return [compact]
    pieces = _OBJ_SPLIT_RE.split(compact)
    chunks: list[str] = []
    cur = ""
    for p in pieces:
        part = p.strip()
        if not part:
            continue
        candidate = f"{cur}\n{part}".strip() if cur else part
        if len(candidate) <= chunk_chars:
            cur = candidate
            continue
        if cur:
            chunks.append(cur)
        if len(part) <= chunk_chars:
            cur = part
            continue
        start = 0
        while start < len(part):
            end = min(len(part), start + chunk_chars)
            chunks.append(part[start:end])
            if end >= len(part):
                break
            start = max(start + 1, end - max(0, overlap_chars))
        cur = ""
    if cur:
        chunks.append(cur)
    return chunks


def _normalize_record(rec: RegistryLlmRecord, default_part: int) -> dict[str, Any]:
    waste_code = (rec.waste_code or "").strip()
    if not re.fullmatch(r"\d{7}", waste_code):
        waste_code = ""
    owner = " ".join((rec.owner or "").replace("\xa0", " ").split()).strip()
    object_name = " ".join((rec.object_name or "").replace("\xa0", " ").split()).strip()
    address = " ".join((rec.address or "").replace("\xa0", " ").split()).strip()
    phones = []
    seen_phones: set[str] = set()
    for p in rec.phones:
        s = " ".join(str(p or "").replace("\xa0", " ").split()).strip(" ,;")
        if not s:
            continue
        key = s.casefold()
        if key in seen_phones:
            continue
        seen_phones.add(key)
        phones.append(s)
    conf = rec.confidence
    if conf < 0:
        conf = 0.0
    if conf > 1:
        conf = 1.0
    part = rec.source_part if rec.source_part in (1, 2) else default_part
    return {
        "id": int(rec.id) if rec.id and rec.id > 0 else 0,
        "owner": owner,
        "object_name": object_name or "—",
        "waste_code": waste_code,
        "waste_type_name": " ".join((rec.waste_type_name or "").split()).strip() or "—",
        "accepts_external_waste": rec.accepts_external_waste if rec.accepts_external_waste is not None else None,
        "address": address,
        "phones": "; ".join(phones),
        "source_part": part,
        "parse_confidence": int(round(conf * 100)),
        "parse_notes": ["llm_openrouter_json"],
    }


def _openrouter_extract_chunk(text_chunk: str, source_part: int, model: str) -> list[dict[str, Any]]:
    if not settings.openrouter_api_key:
        return []
    user_prompt = (
        f"source_part={source_part}\n"
        "Ниже сырой текст реестра. Извлеки записи и верни JSON по схеме.\n\n"
        f"{text_chunk}"
    )
    url = f"{settings.openrouter_base_url}/chat/completions"
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": max(256, int(settings.openrouter_max_output_tokens or 0)),
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": settings.openrouter_system_prompt or DEFAULT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=settings.openrouter_timeout_sec) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    content = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    if not content:
        return []
    raw = _strip_code_fence(str(content))
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("openrouter response is not valid json")
        return []
    try:
        parsed = RegistryLlmResponse.model_validate(obj)
    except ValidationError as e:
        logger.warning("openrouter response schema validation failed: %s", e)
        return []
    out: list[dict[str, Any]] = []
    for rec in parsed.records:
        row = _normalize_record(rec, source_part)
        # Без id и waste_code запись не пригодна для импорта.
        if int(row.get("id") or 0) <= 0:
            continue
        if not str(row.get("waste_code") or "").strip():
            continue
        out.append(row)
    return out


def extract_registry_rows_with_llm(text: str, source_part: int) -> tuple[list[dict[str, Any]], str]:
    if not LLM_FEATURE_ENABLED:
        return [], "disabled"
    if not settings.openrouter_api_key:
        return [], "missing_api_key"
    model = settings.openrouter_model
    fallback_model = settings.openrouter_fallback_model
    max_chars = max(1000, settings.registry_llm_max_chars)
    chunk_chars = max(2000, settings.registry_llm_chunk_chars)
    overlap_chars = max(0, settings.registry_llm_overlap_chars)
    clipped = (text or "")[:max_chars]
    chunks = _chunk_registry_text(clipped, chunk_chars, overlap_chars)
    if not chunks:
        return [], "empty_text"

    all_rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    selected_model = model
    for ch in chunks:
        rows: list[dict[str, Any]] = []
        try:
            rows = _openrouter_extract_chunk(ch, source_part, model)
        except Exception as e:
            logger.warning("openrouter primary model failed: %s", e)
            if fallback_model:
                try:
                    rows = _openrouter_extract_chunk(ch, source_part, fallback_model)
                    selected_model = fallback_model
                except Exception as e2:
                    logger.warning("openrouter fallback model failed: %s", e2)
                    rows = []
        for row in rows:
            key = (
                row.get("source_part"),
                row.get("id"),
                str(row.get("waste_code") or "").strip(),
                str(row.get("owner") or "").strip().casefold(),
                str(row.get("object_name") or "").strip().casefold(),
                str(row.get("address") or "").strip().casefold(),
            )
            if key in seen:
                continue
            seen.add(key)
            all_rows.append(row)
    if not all_rows:
        return [], f"no_rows:{selected_model}"
    return all_rows, f"ok:{selected_model}"


def extract_registry_rows_with_llm_batch(
    seed_rows: list[dict[str, Any]],
    source_part: int,
    *,
    batch_index: int,
    total_batches: int,
    preferred_model: str | None = None,
    fallback_model_override: str | None = None,
    use_fallback: bool = True,
) -> tuple[list[dict[str, Any]], str]:
    """
    LLM-нормализация батча уже распарсенных записей (по 20 и т.п.).
    """
    if not LLM_FEATURE_ENABLED:
        return [], "disabled"
    if not settings.openrouter_api_key:
        return [], "missing_api_key"
    if not seed_rows:
        return [], "empty_batch"

    model = (preferred_model or settings.openrouter_model).strip()
    fallback_model = (
        fallback_model_override.strip()
        if isinstance(fallback_model_override, str)
        else settings.openrouter_fallback_model
    )
    selected_model = model

    compact_seed: list[dict[str, Any]] = []
    for r in seed_rows:
        compact_seed.append(
            {
                "id": int(r.get("id") or 0),
                "waste_code": str(r.get("waste_code") or "").strip(),
                "waste_type_name": str(r.get("waste_type_name") or "").strip(),
                "owner": str(r.get("owner") or "").strip(),
                "object_name": str(r.get("object_name") or "").strip(),
                "address": str(r.get("address") or "").strip(),
                "phones": [x.strip() for x in str(r.get("phones") or "").split(";") if x.strip()],
                "accepts_external_waste": r.get("accepts_external_waste"),
                "source_part": int(r.get("source_part") or source_part),
            }
        )

    user_prompt = (
        f"source_part={source_part}; batch={batch_index}/{total_batches}\n"
        "Ниже candidates (JSON) уже выделенных записей реестра. "
        "Нужно аккуратно нормализовать поля и вернуть JSON строго схемы "
        '{"records": [...]} без потери записей. Сохрани id и waste_code как в candidates. '
        "Одна входная запись -> одна выходная запись.\n\n"
        f"candidates={json.dumps(compact_seed, ensure_ascii=False)}"
    )

    def _run_model(run_model: str) -> list[dict[str, Any]]:
        url = f"{settings.openrouter_base_url}/chat/completions"
        payload = {
            "model": run_model,
            "temperature": 0,
            "max_tokens": max(256, int(settings.openrouter_max_output_tokens or 0)),
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": settings.openrouter_system_prompt or DEFAULT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=settings.openrouter_timeout_sec) as client:
            resp = client.post(url, headers=headers, json=payload)
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                body = (resp.text or "")[:800]
                logger.warning("openrouter batch http %s: %s", resp.status_code, body)
                raise e
            data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            return []
        raw = _strip_code_fence(str(content))
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("openrouter batch response is not valid json")
            return []
        try:
            parsed = RegistryLlmResponse.model_validate(obj)
        except ValidationError as e:
            logger.warning("openrouter batch response schema validation failed: %s", e)
            return []

        out: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for rec in parsed.records:
            row = _normalize_record(rec, source_part)
            rid = int(row.get("id") or 0)
            wcode = str(row.get("waste_code") or "").strip()
            if rid <= 0 or not wcode:
                continue
            key = (rid, wcode, str(row.get("source_part") or source_part))
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
        return out

    try:
        rows = _run_model(model)
    except Exception as e:
        logger.warning("openrouter batch primary model failed: %s", e)
        rows = []

    if use_fallback and (not rows) and fallback_model:
        try:
            rows = _run_model(fallback_model)
            selected_model = fallback_model
        except Exception as e2:
            logger.warning("openrouter batch fallback model failed: %s", e2)
            rows = []

    if not rows:
        return [], f"no_rows:{selected_model}"
    return rows, f"ok:{selected_model}"


def repair_registry_records_with_llm(
    seed_rows: list[dict[str, Any]],
    source_part: int,
    *,
    batch_index: int,
    total_batches: int,
    repair_kind: Literal["address", "full"],
    registry_plaintext: str | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """
    Точечный LLM-repair для уже распарсенных записей (без fallback-модели).
    """
    if not LLM_FEATURE_ENABLED:
        return [], "disabled"
    if not settings.openrouter_api_key:
        return [], "missing_api_key"
    if not seed_rows:
        return [], "empty_batch"

    model = settings.openrouter_model.strip()
    sys_prompt = REPAIR_ADDRESS_SYSTEM_PROMPT if repair_kind == "address" else REPAIR_FULL_SYSTEM_PROMPT

    excerpt_cache: dict[tuple[int, str], str] = {}

    def _source_excerpt_for_row(r: dict[str, Any]) -> str:
        if repair_kind != "full":
            return ""
        pt = (registry_plaintext or "").strip()
        if not pt:
            return ""
        owner_empty = not str(r.get("owner") or "").strip()
        phones_empty = not str(r.get("phones") or "").strip()
        if not owner_empty and not phones_empty:
            return ""
        try:
            oid = int(r.get("id") or 0)
        except (TypeError, ValueError):
            return ""
        if oid <= 0:
            return ""
        wc = str(r.get("waste_code") or "").strip()
        ck = (oid, wc)
        if ck not in excerpt_cache:
            from app.services.registry_record_parser import registry_repair_source_excerpt

            # Для телефонов нужен больший контекст выше «Объект» (часто тел./факс у собственника или в шапке карточки).
            if phones_empty:
                excerpt_cache[ck] = registry_repair_source_excerpt(
                    pt,
                    oid,
                    wc if wc else None,
                    before=7200,
                    after=10_000,
                    max_chars=12_000,
                )
            else:
                excerpt_cache[ck] = registry_repair_source_excerpt(
                    pt,
                    oid,
                    wc if wc else None,
                    max_chars=9000,
                )
        return excerpt_cache[ck]

    compact_seed: list[dict[str, Any]] = []
    for r in seed_rows:
        item: dict[str, Any] = {
            "id": int(r.get("id") or 0),
            "waste_code": str(r.get("waste_code") or "").strip(),
            "waste_type_name": str(r.get("waste_type_name") or "").strip(),
            "owner": str(r.get("owner") or "").strip(),
            "object_name": str(r.get("object_name") or "").strip(),
            "address": str(r.get("address") or "").strip(),
            "phones": [x.strip() for x in str(r.get("phones") or "").split(";") if x.strip()],
            "accepts_external_waste": r.get("accepts_external_waste"),
            "source_part": int(r.get("source_part") or source_part),
        }
        ex = _source_excerpt_for_row(r)
        if ex:
            item["source_excerpt"] = ex
        compact_seed.append(item)

    user_prompt = (
        f"source_part={source_part}; repair_batch={batch_index}/{total_batches}; mode={repair_kind}\n"
        "Верни JSON строго формата {\"records\": [...]} без потери записей. "
        "Одна входная запись -> одна выходная запись; id и waste_code совпадают с candidates.\n\n"
        f"candidates={json.dumps(compact_seed, ensure_ascii=False)}"
    )
    if repair_kind == "full" and any(not str(r.get("phones") or "").strip() for r in seed_rows):
        user_prompt += (
            "\n\nВ этом батче есть записи с пустым phones: для каждой такой записи просмотри source_excerpt "
            "(и при необходимости соседние строки того же фрагмента) и перенеси все явно видимые телефоны/факс "
            "в поле phones массивом строк. Номер может быть разбит переносами строк — восстанови целый номер, "
            "если части явно относятся к этой карточке; не подтягивай номера соседних объектов. "
            "Если в тексте номеров нет — не придумывай."
        )

    url = f"{settings.openrouter_base_url}/chat/completions"
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": max(256, int(settings.openrouter_max_output_tokens or 0)),
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=settings.openrouter_timeout_sec) as client:
            resp = client.post(url, headers=headers, json=payload)
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                body = (resp.text or "")[:800]
                logger.warning("openrouter repair http %s: %s", resp.status_code, body)
                raise e
            data = resp.json()
    except Exception as e:
        logger.warning("openrouter repair failed (%s): %s", repair_kind, e)
        return [], f"no_rows:{model}"

    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        return [], f"no_rows:{model}"
    raw = _strip_code_fence(str(content))
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("openrouter repair response is not valid json")
        return [], f"no_rows:{model}"
    try:
        parsed = RegistryLlmResponse.model_validate(obj)
    except ValidationError as e:
        logger.warning("openrouter repair schema validation failed: %s", e)
        return [], f"no_rows:{model}"

    out: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for rec in parsed.records:
        row = _normalize_record(rec, source_part)
        rid = int(row.get("id") or 0)
        wcode = str(row.get("waste_code") or "").strip()
        if rid <= 0 or not wcode:
            continue
        key = (rid, wcode, str(row.get("source_part") or source_part))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    if not out:
        return [], f"no_rows:{model}"
    return out, f"ok:{model}"


