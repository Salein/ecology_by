/**
 * Базовый URL API без завершающего «/».
 * - `__RELATIVE__` или пустая строка → относительные пути `/api/...` (тот же host, что у страницы — нужно за nginx в Docker).
 * - иначе полный URL (локальный uvicorn, другой домен).
 */
export function getApiBase(): string {
  const raw = process.env.NEXT_PUBLIC_API_URL;
  if (raw === undefined || raw === null) {
    return "http://localhost:8000".replace(/\/$/, "");
  }
  const v = String(raw).trim();
  if (v === "" || v === "__RELATIVE__") {
    return "";
  }
  return v.replace(/\/$/, "");
}

/** Полный URL для fetch: либо `origin + path`, либо только `path` (если API на том же origin). */
export function apiUrl(path: string): string {
  const b = getApiBase();
  const p = path.startsWith("/") ? path : `/${path}`;
  if (!b) return p;
  return `${b}${p}`;
}

export const cred = { credentials: "include" as const };
