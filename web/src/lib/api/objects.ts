import { apiUrl, cred } from "./client";
import { createTimeoutLinkedAbort, isAbortError } from "./http";

const SEARCH_FETCH_MS = 180_000;
const WASTE_SUGGEST_FETCH_MS = 15_000;

export type WasteObjectRow = {
  id: number;
  owner: string;
  object_name: string;
  address?: string | null;
  phones?: string | null;
  waste_code?: string | null;
  waste_type_name?: string | null;
  accepts_external_waste?: boolean | null;
  /** Совместимое поле: приоритетно по дорогам, иначе по воздуху */
  distance_km?: number | null;
  /** По прямой (Haversine) */
  distance_air_km?: number | null;
  /** По дорогам (OSRM) */
  distance_road_km?: number | null;
  /** Причина, почему по дорогам не удалось */
  distance_road_error?: string | null;
  /** Любая дистанция в выдаче оценочная */
  distance_is_approx?: boolean;
  /** Ориентировочный разброс: ± км */
  distance_spread_km?: number | null;
  distance_spread_note?: string | null;
  /** Пояснение, если км посчитаны по справочнику НП/области, а не по точному геокоду */
  distance_note?: string | null;
};

export type WasteSuggestItem = {
  waste_code: string;
  waste_type_name: string;
};

export async function searchObjects(params: {
  query: string;
  wasteCode?: string | null;
  lat?: number;
  lon?: number;
  /** Отмена снаружи (например, начался импорт PDF) — выбросит AbortError, а не «таймаут». */
  signal?: AbortSignal;
}): Promise<WasteObjectRow[]> {
  const { signal, dispose, timedOut } = createTimeoutLinkedAbort(SEARCH_FETCH_MS, params.signal);
  const parent = params.signal;
  try {
    const r = await fetch(apiUrl("/api/v1/objects/search"), {
      ...cred,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal,
      body: JSON.stringify({
        query: params.query,
        waste_code: params.wasteCode ?? null,
        lat: params.lat == null ? null : Number(params.lat),
        lon: params.lon == null ? null : Number(params.lon),
      }),
    });
    if (!r.ok) {
      const hint =
        r.status >= 500
          ? `Ошибка сервера (${r.status}). Смотрите логи API: docker compose logs -f api`
          : `Запрос отклонён (${r.status})`;
      throw new Error(`Поиск: ${hint}`);
    }
    const data = (await r.json()) as { items: WasteObjectRow[] };
    return data.items;
  } catch (e) {
    if (isAbortError(e)) {
      if (parent?.aborted && !timedOut()) {
        throw new DOMException("Search cancelled", "AbortError");
      }
      throw new Error(
        "Поиск прерван по таймауту (до 3 мин). Возможно, идёт геокодирование многих адресов — подождите и снимите точку на карте или сузьте запрос.",
      );
    }
    throw e;
  } finally {
    dispose();
  }
}

export async function fetchWasteSuggestions(
  query: string,
  limit = 12,
  signal?: AbortSignal,
): Promise<WasteSuggestItem[]> {
  const q = query.trim();
  if (q.length < 2) return [];
  const { signal: inner, dispose } = createTimeoutLinkedAbort(WASTE_SUGGEST_FETCH_MS, signal);
  try {
    const qs = new URLSearchParams({ q, limit: String(Math.max(1, Math.min(30, limit))) }).toString();
    const r = await fetch(apiUrl(`/api/v1/objects/waste-suggest?${qs}`), {
      ...cred,
      cache: "no-store",
      signal: inner,
    });
    if (!r.ok) throw new Error(`waste suggest failed: ${r.status}`);
    const data = (await r.json()) as { items?: WasteSuggestItem[] };
    return Array.isArray(data.items) ? data.items : [];
  } finally {
    dispose();
  }
}
