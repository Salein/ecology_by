import { apiUrl, cred } from "./client";
import { createTimeoutLinkedAbort, isAbortError } from "./http";

export type RegistryCacheMeta = {
  updated_at?: string;
  record_count: number;
  accepts_true_count?: number;
  accepts_false_count?: number;
  accepts_unknown_count?: number;
  sources?: string[];
  source_signature?: string | null;
};

const REGISTRY_CACHE_FETCH_MS = 12_000;

export type FetchRegistryCacheMetaResult =
  | { ok: true; cache: RegistryCacheMeta | null; registry_import_in_progress: boolean }
  | { ok: false; reason: string };

/** С таймаутом и различием «пустой кэш» / «сервер недоступен». */
export async function fetchRegistryCacheMetaResult(): Promise<FetchRegistryCacheMetaResult> {
  const { signal, dispose } = createTimeoutLinkedAbort(REGISTRY_CACHE_FETCH_MS, undefined);
  try {
    const r = await fetch(apiUrl("/api/v1/registry/cache"), {
      ...cred,
      signal,
      cache: "no-store",
    });
    if (!r.ok) {
      return { ok: false, reason: `ответ ${r.status}` };
    }
    const data = (await r.json()) as {
      cache: RegistryCacheMeta | null;
      registry_import_in_progress?: boolean;
    };
    return {
      ok: true,
      cache: data.cache,
      registry_import_in_progress: Boolean(data.registry_import_in_progress),
    };
  } catch (e) {
    if (isAbortError(e)) {
      return { ok: false, reason: "таймаут" };
    }
    return { ok: false, reason: "сеть или CORS" };
  } finally {
    dispose();
  }
}

export async function fetchRegistryCacheMeta(): Promise<RegistryCacheMeta | null> {
  const res = await fetchRegistryCacheMetaResult();
  return res.ok ? res.cache : null;
}

export async function clearRegistryCache(): Promise<void> {
  const r = await fetch(apiUrl("/api/v1/registry/cache"), {
    ...cred,
    method: "DELETE",
    cache: "no-store",
  });
  if (!r.ok) {
    let msg = `clear cache: ${r.status}`;
    try {
      const j = (await r.json()) as { detail?: string };
      if (typeof j.detail === "string") msg = j.detail;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  clearRegistryClientState();
}

const REGISTRY_CLIENT_STATE_KEYS = [
  "ecology_registry_cache_meta",
  "ecology_registry_import_status",
  "ecology_registry_import_json",
  "ecology_registry_rows_snapshot",
] as const;

export function clearRegistryClientState(): void {
  if (typeof window === "undefined") return;
  for (const k of REGISTRY_CLIENT_STATE_KEYS) {
    try {
      localStorage.removeItem(k);
    } catch {
      /* ignore */
    }
    try {
      sessionStorage.removeItem(k);
    } catch {
      /* ignore */
    }
  }
}

export type RegistryImportStatus = {
  status: string;
  progress: number;
  message?: string;
  error?: string | null;
  records_count?: number;
  metrics?: {
    stage?: string;
    queue_position?: number;
    queue_size?: number;
    queue_eta_sec?: number;
    avg_job_sec?: number;
    ocr_total?: number;
    ocr_done?: number;
    ocr_inflight?: number;
    ocr_workers?: number;
    file_name?: string;
    file_index?: number;
    files_total?: number;
    files_done?: number;
    page?: number;
    pages_total?: number;
    llm_batch_index?: number;
    llm_batches_total?: number;
    llm_batch_coverage_pct?: number;
    llm_parse_conf_below?: number;
    llm_selective_targets_total?: number;
    llm_repair_rows_this_file?: number;
    llm_rows_merged_total?: number;
    llm_post_checkbox_targets?: number;
    llm_post_checkbox_rows_merged?: number;
    llm_post_checkbox_batches?: number;
    parsed_records?: number;
    saved_records?: number;
    stage_done?: number;
    stage_total?: number;
    stage_unit?: string;
    stage_eta_sec?: number | null;
    done?: number;
    total?: number;
    rows_per_sec?: number;
    eta_sec?: number | null;
    nominatim_calls?: number;
    nominatim_hit?: number;
    nominatim_miss?: number;
    cache_hit?: number;
    approx_hit?: number;
    addr_skipped?: number;
    cached_miss_skip?: number;
    budget_skip?: number;
    checkpoints?: number;
    db_snapshots?: number;
    geocache_flushes?: number;
    parse_rows_total?: number;
    parse_owner_empty?: number;
    parse_address_empty?: number;
    parse_address_no_locality?: number;
    parse_phones_empty?: number;
    parse_object_placeholder?: number;
    parse_low_confidence?: number;
    parse_needs_review?: number;
    parse_repair_pass_rows?: number;
    llm_calls?: number;
    llm_success?: number;
    llm_fail?: number;
    llm_rows_accepted?: number;
    llm_rows_rejected?: number;
    llm_enrich_candidates?: number;
    llm_rows_applied?: number;
    extract_sec?: number;
    parse_sec?: number;
    checkbox_sec?: number;
    merge_sec?: number;
    geocode_sec?: number;
    total_sec?: number;
  };
};

const REGISTRY_IMPORT_STATUS_FETCH_MS = 25_000;

export async function fetchRegistryImportStatus(
  jobId: string,
  signal?: AbortSignal,
): Promise<RegistryImportStatus> {
  const { signal: inner, dispose } = createTimeoutLinkedAbort(REGISTRY_IMPORT_STATUS_FETCH_MS, signal);
  try {
    const r = await fetch(apiUrl(`/api/v1/registry/import/${jobId}`), {
      ...cred,
      signal: inner,
      cache: "no-store",
    });
    if (!r.ok) throw new Error(`import status failed: ${r.status}`);
    return (await r.json()) as RegistryImportStatus;
  } catch (e) {
    if (isAbortError(e)) {
      throw new Error("import status: timed out (network)");
    }
    throw e;
  } finally {
    dispose();
  }
}

export type RegistryImportPostResult =
  | { skipped: true; message?: string; cache: RegistryCacheMeta | null }
  | { skipped: false; job_id: string };

export type RegistryUploadProgress = {
  pct: number;
  loadedBytes: number;
  totalBytes: number;
  speedMbps: number | null;
  etaSec: number | null;
  phase: "uploading" | "waiting_server";
};

/** Совпадает с лимитом одного файла на API (`MAX_PDF_BYTES` в registry router). */
export const REGISTRY_IMPORT_MAX_FILE_BYTES = 120 * 1024 * 1024;

/**
 * Целевой размер одной multipart-загрузки (сумма файлов).
 * Ниже ~100 МБ с запасом на boundary multipart — чтобы не ловить 413 через Cloudflare-туннель.
 */
export const REGISTRY_IMPORT_BATCH_MAX_BYTES = 85 * 1024 * 1024;

/** Максимум файлов в одном запросе (защита от гигантских форм и таймаутов). */
export const REGISTRY_IMPORT_BATCH_MAX_FILES = 60;

/**
 * Делит выбранные файлы на партии для последовательной загрузки (меньше 413 и стабильнее сеть).
 * Файл крупнее лимита партии уходит отдельным запросом (если не превышает лимит одного файла на сервере).
 */
export function chunkFilesForRegistryImport(files: File[]): File[][] {
  const batches: File[][] = [];
  let cur: File[] = [];
  let curBytes = 0;

  const flush = () => {
    if (cur.length) {
      batches.push(cur);
      cur = [];
      curBytes = 0;
    }
  };

  for (const f of files) {
    if (f.size > REGISTRY_IMPORT_MAX_FILE_BYTES) {
      throw new Error(
        `Файл «${f.name}» слишком большой (${(f.size / (1024 * 1024)).toFixed(1)} МБ). На сервере допускается до ${Math.round(REGISTRY_IMPORT_MAX_FILE_BYTES / (1024 * 1024))} МБ на файл.`,
      );
    }

    if (f.size > REGISTRY_IMPORT_BATCH_MAX_BYTES) {
      flush();
      batches.push([f]);
      continue;
    }

    if (
      cur.length > 0 &&
      (curBytes + f.size > REGISTRY_IMPORT_BATCH_MAX_BYTES || cur.length >= REGISTRY_IMPORT_BATCH_MAX_FILES)
    ) {
      flush();
    }

    cur.push(f);
    curBytes += f.size;
  }
  flush();
  return batches;
}

/** Доля прогресса (0–100) для партии `batchIndex` из `batchTotal`: этап отправки или ожидание сервера. */
export function registryImportBatchProgress(
  batchIndex: number,
  batchTotal: number,
  phase: "upload" | "poll",
  uploadPct0to100: number,
  jobProgress0to100: number,
): number {
  if (batchTotal <= 0) return 0;
  const share = 100 / batchTotal;
  const base = batchIndex * share;
  if (phase === "upload") {
    return Math.min(100, Math.round(base + share * 0.35 * (uploadPct0to100 / 100)));
  }
  return Math.min(100, Math.round(base + share * (0.35 + 0.65 * (jobProgress0to100 / 100))));
}

/** Загрузка файлов реестра (PDF/изображения/HTML/TXT) с прогрессом отправки (0–100). */
export function postRegistryImportWithUploadProgress(
  files: File[],
  onUploadProgress: (progress: RegistryUploadProgress) => void,
  importMode: "replace" | "append" = "replace",
): Promise<RegistryImportPostResult> {
  const url = apiUrl("/api/v1/registry/import");
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const startedAtMs = Date.now();
    xhr.open("POST", url);
    xhr.withCredentials = true;
    xhr.responseType = "json";
    let waitingServerTimer: ReturnType<typeof setInterval> | null = null;
    let lastLoaded = 0;
    let lastTotal = 0;
    let uploadFinished = false;
    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable) {
        const loaded = Number(ev.loaded || 0);
        const total = Number(ev.total || 0);
        lastLoaded = loaded;
        lastTotal = total;
        const pct = total > 0 ? Math.min(100, Math.round((100 * loaded) / total)) : 0;
        const elapsedSec = Math.max(0.001, (Date.now() - startedAtMs) / 1000);
        const bytesPerSec = loaded > 0 ? loaded / elapsedSec : 0;
        const speedMbps = bytesPerSec > 0 ? Number(((bytesPerSec * 8) / 1_000_000).toFixed(2)) : null;
        const etaSec = bytesPerSec > 0 && total > loaded ? Math.round((total - loaded) / bytesPerSec) : null;
        onUploadProgress({
          pct,
          loadedBytes: loaded,
          totalBytes: total,
          speedMbps,
          etaSec,
          phase: "uploading",
        });
      }
    };
    xhr.upload.onloadend = () => {
      if (uploadFinished) return;
      uploadFinished = true;
      onUploadProgress({
        pct: 100,
        loadedBytes: lastTotal > 0 ? lastTotal : lastLoaded,
        totalBytes: lastTotal > 0 ? lastTotal : lastLoaded,
        speedMbps: null,
        etaSec: 0,
        phase: "waiting_server",
      });
      waitingServerTimer = setInterval(() => {
        onUploadProgress({
          pct: 100,
          loadedBytes: lastTotal > 0 ? lastTotal : lastLoaded,
          totalBytes: lastTotal > 0 ? lastTotal : lastLoaded,
          speedMbps: null,
          etaSec: null,
          phase: "waiting_server",
        });
      }, 1200);
    };
    xhr.onload = () => {
      if (waitingServerTimer) {
        clearInterval(waitingServerTimer);
        waitingServerTimer = null;
      }
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
        let detail = "";
        try {
          if (typeof xhr.response === "object" && xhr.response !== null) {
            const d = (xhr.response as { detail?: unknown }).detail;
            if (typeof d === "string") detail = d;
          } else if (xhr.responseText) {
            const parsed = JSON.parse(xhr.responseText) as { detail?: unknown };
            if (typeof parsed.detail === "string") detail = parsed.detail;
          }
        } catch {
          /* ignore parse errors */
        }
        if (xhr.status === 413) {
          reject(
            new Error(
              "Пакет файлов слишком большой (HTTP 413). Уменьшите размер партии или загружайте меньшими пачками. " +
                "Если работаете через Cloudflare-туннель, лимит обычно около 100MB на запрос.",
            ),
          );
          return;
        }
        const suffix = detail ? `: ${detail}` : "";
        reject(new Error(`Ошибка загрузки: ${xhr.status}${suffix}`));
      }
    };
    xhr.onerror = () => {
      if (waitingServerTimer) {
        clearInterval(waitingServerTimer);
        waitingServerTimer = null;
      }
      reject(new Error("Сеть: не удалось отправить файлы"));
    };
    const fd = new FormData();
    fd.append("import_mode", importMode);
    for (const f of files) fd.append("files", f);
    xhr.send(fd);
  });
}
