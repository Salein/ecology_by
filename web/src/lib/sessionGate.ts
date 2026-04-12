/**
 * Флаговая cookie на домене Next.js — только для middleware (редирект на /).
 * Сессия и JWT хранятся на API в HttpOnly cookie; регистрационные данные — только в БД/файле на сервере.
 */
export const SESSION_GATE_COOKIE = "ecology_has_session";

function gateCookieSecureSuffix(): string {
  return typeof window !== "undefined" && window.location.protocol === "https:" ? "; Secure" : "";
}

export function setSessionGate(): void {
  if (typeof document === "undefined") return;
  const maxAge = 60 * 60 * 24 * 7;
  document.cookie = `${SESSION_GATE_COOKIE}=1; Path=/; Max-Age=${maxAge}; SameSite=Lax${gateCookieSecureSuffix()}`;
}

export function clearSessionGate(): void {
  if (typeof document === "undefined") return;
  document.cookie = `${SESSION_GATE_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax${gateCookieSecureSuffix()}`;
}

/** Удаляет устаревший токен из localStorage (раньше клиент сохранял JWT). */
export function clearLegacyAuthStorage(): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem("ecology_auth_token");
  } catch {
    /* ignore */
  }
}
