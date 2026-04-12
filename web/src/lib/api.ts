/** Сессия — HttpOnly cookie на API; hostname лучше совпадать со страницей (localhost с localhost). */
export function getApiBase(): string {
  return (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
}

const base = getApiBase;

const cred = { credentials: "include" as const };

export type WasteObjectRow = {
  id: number;
  owner: string;
  object_name: string;
  address?: string | null;
  phones?: string | null;
  waste_code?: string | null;
  waste_type_name?: string | null;
  accepts_external_waste?: boolean;
  distance_km?: number | null;
  /** Пояснение, если км посчитаны по справочнику НП/области, а не по точному геокоду */
  distance_note?: string | null;
};

const SEARCH_FETCH_MS = 180_000;

export async function searchObjects(params: {
  query: string;
  lat?: number;
  lon?: number;
}): Promise<WasteObjectRow[]> {
  const ctrl = new AbortController();
  const id = setTimeout(() => ctrl.abort(), SEARCH_FETCH_MS);
  try {
    const r = await fetch(`${base()}/api/v1/objects/search`, {
      ...cred,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: ctrl.signal,
      body: JSON.stringify({
        query: params.query,
        waste_code: null,
        lat: params.lat == null ? null : Number(params.lat),
        lon: params.lon == null ? null : Number(params.lon),
      }),
    });
    if (!r.ok) throw new Error(`search failed: ${r.status}`);
    const data = (await r.json()) as { items: WasteObjectRow[] };
    return data.items;
  } catch (e) {
    const aborted =
      (e instanceof DOMException && e.name === "AbortError") ||
      (e instanceof Error && e.name === "AbortError");
    if (aborted) {
      throw new Error(
        "Поиск прерван по таймауту (до 3 мин). Возможно, идёт геокодирование многих адресов — подождите и снимите точку на карте или сузьте запрос.",
      );
    }
    throw e;
  } finally {
    clearTimeout(id);
  }
}

export async function reverseGeocode(lat: number, lon: number): Promise<string | null> {
  const u = new URL(`${base()}/api/v1/geocode/reverse`);
  u.searchParams.set("lat", String(lat));
  u.searchParams.set("lon", String(lon));
  const r = await fetch(u.toString(), { ...cred });
  if (!r.ok) throw new Error(`reverse geocode failed: ${r.status}`);
  const data = (await r.json()) as { display_name: string | null };
  const name = data.display_name?.trim();
  return name || null;
}

export type RegistryCacheMeta = {
  updated_at?: string;
  record_count: number;
  sources?: string[];
  source_signature?: string | null;
};

const REGISTRY_CACHE_FETCH_MS = 12_000;

export type FetchRegistryCacheMetaResult =
  | { ok: true; cache: RegistryCacheMeta | null }
  | { ok: false; reason: string };

/** С таймаутом и различием «пустой кэш» / «сервер недоступен». */
export async function fetchRegistryCacheMetaResult(): Promise<FetchRegistryCacheMetaResult> {
  const ctrl = new AbortController();
  const id = setTimeout(() => ctrl.abort(), REGISTRY_CACHE_FETCH_MS);
  try {
    const r = await fetch(`${base()}/api/v1/registry/cache`, {
      ...cred,
      signal: ctrl.signal,
    });
    if (!r.ok) {
      return { ok: false, reason: `ответ ${r.status}` };
    }
    const data = (await r.json()) as { cache: RegistryCacheMeta | null };
    return { ok: true, cache: data.cache };
  } catch (e) {
    const aborted =
      (e instanceof DOMException && e.name === "AbortError") ||
      (e instanceof Error && e.name === "AbortError");
    if (aborted) {
      return { ok: false, reason: "таймаут" };
    }
    return { ok: false, reason: "сеть или CORS" };
  } finally {
    clearTimeout(id);
  }
}

export async function fetchRegistryCacheMeta(): Promise<RegistryCacheMeta | null> {
  const res = await fetchRegistryCacheMetaResult();
  return res.ok ? res.cache : null;
}

export type RegistryImportStatus = {
  status: string;
  progress: number;
  message?: string;
  error?: string | null;
  records_count?: number;
};

export async function fetchRegistryImportStatus(jobId: string): Promise<RegistryImportStatus> {
  const r = await fetch(`${base()}/api/v1/registry/import/${jobId}`, { ...cred });
  if (!r.ok) throw new Error(`import status failed: ${r.status}`);
  return (await r.json()) as RegistryImportStatus;
}

export type RegistryImportPostResult =
  | { skipped: true; message?: string; cache: RegistryCacheMeta | null }
  | { skipped: false; job_id: string };

/** Загрузка PDF с прогрессом отправки (0–100). При skipped — кэш не менялся, job не создаётся. */
export function postRegistryImportWithUploadProgress(
  files: File[],
  onUploadPercent: (pct: number) => void,
): Promise<RegistryImportPostResult> {
  const url = `${base()}/api/v1/registry/import`;
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.withCredentials = true;
    xhr.responseType = "json";
    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable) {
        onUploadPercent(Math.min(100, Math.round((100 * ev.loaded) / ev.total)));
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        let body: {
          skipped?: boolean;
          job_id?: string | null;
          message?: string;
          cache?: RegistryCacheMeta | null;
        };
        try {
          body =
            typeof xhr.response === "object" && xhr.response !== null
              ? (xhr.response as typeof body)
              : (JSON.parse(xhr.responseText || "{}") as typeof body);
        } catch {
          reject(new Error("Некорректный ответ сервера"));
          return;
        }
        if (body?.skipped === true) {
          resolve({
            skipped: true,
            message: body.message,
            cache: body.cache ?? null,
          });
          return;
        }
        if (body?.job_id) resolve({ skipped: false, job_id: body.job_id });
        else reject(new Error("Нет job_id в ответе"));
      } else {
        reject(new Error(`Ошибка загрузки: ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new Error("Сеть: не удалось отправить файлы"));
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    xhr.send(fd);
  });
}

export type AdminUserRow = {
  id: number;
  email: string;
  name: string;
  role: "user" | "admin";
  created_at: string;
  blocked: boolean;
  /** Учётная запись владельца (BOOTSTRAP_OWNER_EMAIL) — удалять нельзя */
  protected_account: boolean;
};

export async function fetchAdminUsers(): Promise<AdminUserRow[]> {
  const r = await fetch(`${base()}/api/v1/admin/users`, { ...cred });
  if (!r.ok) throw new Error(`admin users: ${r.status}`);
  return (await r.json()) as AdminUserRow[];
}

export type AdminUserPatch = {
  role?: "user" | "admin";
  blocked?: boolean;
};

export async function patchAdminUser(userId: number, patch: AdminUserPatch): Promise<AdminUserRow> {
  const r = await fetch(`${base()}/api/v1/admin/users/${userId}`, {
    ...cred,
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!r.ok) {
    let msg = `patch user: ${r.status}`;
    try {
      const j = (await r.json()) as { detail?: string };
      if (typeof j.detail === "string") msg = j.detail;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return (await r.json()) as AdminUserRow;
}

export async function deleteAdminUser(userId: number): Promise<void> {
  const r = await fetch(`${base()}/api/v1/admin/users/${userId}`, {
    ...cred,
    method: "DELETE",
  });
  if (!r.ok) {
    let msg = `delete user: ${r.status}`;
    try {
      const j = (await r.json()) as { detail?: string };
      if (typeof j.detail === "string") msg = j.detail;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
}

export async function authLogout(): Promise<void> {
  await fetch(`${base()}/api/v1/auth/logout`, { ...cred, method: "POST" });
}
