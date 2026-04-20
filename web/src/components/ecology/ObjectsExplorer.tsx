"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import {
  fetchRegistryCacheMetaResult,
  fetchRegistryImportStatus,
  postRegistryImportWithUploadProgress,
  reverseGeocode,
  searchObjects,
  type RegistryCacheMeta,
  type RegistryImportStatus,
  type WasteObjectRow,
} from "@/lib/api";
import {
  formatWasteTypeDisplay,
} from "./formatters";
import {
  AddressCell,
  AirDistanceCell,
  CodeCell,
  ObjectCell,
  OwnerCell,
  PhonesCell,
  RoadDistanceCell,
} from "./resultCells";
import { WasteTypeField } from "./wasteTypeField";

const LocationMapModal = dynamic(
  () => import("./LocationMapModal").then((m) => m.LocationMapModal),
  { ssr: false },
);

const EM_DASH = "—";

const LOCATION_PLACEHOLDER = "Выберите местоположение объекта";

/** Сетка строки результатов: код | собственник | объект | адрес | телефоны | по воздуху | по дорогам */
const RESULT_GRID =
  "sm:grid-cols-[minmax(5rem,5.5rem)_minmax(14.2rem,1.15fr)_minmax(14.2rem,1.15fr)_minmax(16.2rem,1.4fr)_minmax(10.1rem,0.95fr)_minmax(calc(7.4rem_-_10px),0.8fr)_minmax(calc(7.4rem_-_10px),0.8fr)]";

/** Под строкой с «—», если точка на карте выбрана, а км не посчитались */
const DISTANCE_NOT_CALCULATED_NOTE = "Расстояние не удалось рассчитать";
const ROAD_DISTANCE_NOT_CALCULATED_NOTE = "По дорогам: расчёт не выполнен";

function formatEta(sec: number | null | undefined): string {
  if (sec == null || !Number.isFinite(sec) || sec < 0) return EM_DASH;
  const s = Math.max(0, Math.round(sec));
  const mm = Math.floor(s / 60);
  const ss = s % 60;
  if (mm <= 0) return `${ss} c`;
  return `${mm}м ${ss.toString().padStart(2, "0")}с`;
}

function ResultsSkeleton() {
  return (
    <ul className="flex flex-col gap-4" aria-hidden>
      {Array.from({ length: 7 }).map((_, i) => (
        <li
          key={i}
          className={`grid animate-pulse grid-cols-1 gap-3 rounded-2xl border border-emerald-100/90 bg-white/90 p-4 shadow-sm shadow-emerald-900/5 ${RESULT_GRID} sm:items-start sm:gap-x-5 sm:gap-y-3`}
        >
          <div className="h-5 w-10 rounded bg-emerald-100 sm:pt-0.5" />
          <div className="h-4 w-full max-w-full rounded bg-emerald-100 sm:pt-0.5" />
          <div className="h-20 w-full rounded-xl bg-emerald-100" />
          <div className="h-14 w-full rounded-lg bg-emerald-100" />
          <div className="h-10 w-full rounded-lg bg-emerald-100" />
          <div className="h-10 w-14 justify-self-end rounded-xl bg-emerald-100 sm:justify-self-end sm:pt-0.5" />
          <div className="h-10 w-20 justify-self-end rounded-xl bg-emerald-100 sm:justify-self-end sm:pt-0.5" />
        </li>
      ))}
    </ul>
  );
}

function DistanceCalculationLoader() {
  const leaves = [
    { left: "17%", top: "18%", delay: "0ms" },
    { left: "26%", top: "12%", delay: "160ms" },
    { left: "35%", top: "10%", delay: "320ms" },
    { left: "45%", top: "11%", delay: "520ms" },
    { left: "56%", top: "13%", delay: "700ms" },
    { left: "67%", top: "17%", delay: "860ms" },
    { left: "74%", top: "24%", delay: "1020ms" },
    { left: "63%", top: "26%", delay: "1180ms" },
    { left: "51%", top: "25%", delay: "1320ms" },
    { left: "39%", top: "24%", delay: "1460ms" },
    { left: "29%", top: "23%", delay: "1600ms" },
    { left: "21%", top: "25%", delay: "1740ms" },
  ];

  return (
    <div
      className="relative mx-auto w-fit max-w-full overflow-hidden rounded-2xl border border-emerald-200/80 bg-gradient-to-br from-emerald-50 via-lime-50 to-amber-50 shadow-sm shadow-emerald-900/5"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div className="relative inline-block max-w-full">
        {/* eslint-disable-next-line @next/next/no-img-element -- локальный ассет, без layout shift */}
        <img
          src="/loader/eco-loader.png"
          alt=""
          width={756}
          height={834}
          decoding="async"
          className="eco-loader-image block h-auto max-h-[min(52vh,560px)] w-auto max-w-full"
        />
        <div className="eco-loader-light pointer-events-none absolute inset-0 bg-gradient-to-r from-emerald-300/10 via-amber-100/35 to-lime-200/20" />
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-emerald-950/45 via-emerald-900/20 to-transparent" />
        <div className="pointer-events-none absolute inset-0">
          {leaves.map((leaf, i) => (
            <span
              key={i}
              className="eco-loader-leaf absolute h-2.5 w-2.5 rounded-full bg-lime-200/90 shadow-[0_0_0_1px_rgba(16,185,129,0.3)]"
              style={{ left: leaf.left, top: leaf.top, animationDelay: leaf.delay }}
            />
          ))}
        </div>
        <div className="absolute inset-x-0 bottom-0 p-3 sm:p-4">
          <div className="inline-flex max-w-full flex-col rounded-xl border border-emerald-100/60 bg-emerald-950/35 px-3 py-2 backdrop-blur-[1px]">
            <p className="text-sm font-semibold text-emerald-50">Идёт расчёт расстояний…</p>
            <p className="mt-0.5 text-xs leading-relaxed text-emerald-100/90">
              Подбираем ближайшие объекты и считаем расстояние по воздуху и по дорогам.
            </p>
          </div>
        </div>
      </div>
      <style jsx>{`
        .eco-loader-image {
          animation: ecoZoomPan 7s ease-in-out infinite;
          transform-origin: center 40%;
        }
        .eco-loader-light {
          animation: lightPulse 3.4s ease-in-out infinite;
        }
        .eco-loader-leaf {
          opacity: 0.15;
          transform: scale(0.4);
          animation: leafBloom 2.2s ease-in-out infinite;
        }
        @keyframes leafBloom {
          0% {
            opacity: 0.12;
            transform: scale(0.35);
          }
          35% {
            opacity: 0.95;
            transform: scale(1);
          }
          70% {
            opacity: 1;
            transform: scale(1.1);
          }
          100% {
            opacity: 0.2;
            transform: scale(0.45);
          }
        }
        @keyframes lightPulse {
          0%,
          100% {
            opacity: 0.45;
          }
          50% {
            opacity: 0.82;
          }
        }
        @keyframes ecoZoomPan {
          0%,
          100% {
            transform: scale(1) translate3d(0, 0, 0);
          }
          50% {
            transform: scale(1.045) translate3d(0, -1.5%, 0);
          }
        }
      `}</style>
    </div>
  );
}

export type ObjectsExplorerProps = {
  /** Только администратор может загружать PDF реестра */
  canImportRegistry: boolean;
};

export function ObjectsExplorer({ canImportRegistry }: ObjectsExplorerProps) {
  const { user, logout } = useAuth();
  const fileRef = useRef<HTMLInputElement>(null);
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [lat, setLat] = useState<number | undefined>(undefined);
  const [lon, setLon] = useState<number | undefined>(undefined);
  const [addressLabel, setAddressLabel] = useState("");
  const [mapOpen, setMapOpen] = useState(false);
  const [rows, setRows] = useState<WasteObjectRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cacheMeta, setCacheMeta] = useState<RegistryCacheMeta | null>(null);
  const [cacheMetaReady, setCacheMetaReady] = useState(false);
  const [registryMetaError, setRegistryMetaError] = useState<string | null>(null);
  const [importBusy, setImportBusy] = useState(false);
  const [importProgress, setImportProgress] = useState(0);
  const [importMessage, setImportMessage] = useState("");
  const [importError, setImportError] = useState<string | null>(null);
  const [importMetrics, setImportMetrics] = useState<RegistryImportStatus["metrics"] | null>(null);

  const refreshAddress = useCallback(async (la: number, lo: number) => {
    setAddressLabel(`${la.toFixed(4)}, ${lo.toFixed(4)}`);
    try {
      const name = await reverseGeocode(la, lo);
      if (name) setAddressLabel(name);
    } catch {
      /* координаты уже в подписи */
    }
  }, []);

  const runSearch = useCallback(async () => {
    const q = query.trim();
    if (!q) {
      setRows([]);
      setError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const items = await searchObjects({
        query: q,
        lat,
        lon,
      });
      setRows(items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка запроса");
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [query, lat, lon]);

  const submitQuery = useCallback(() => {
    const next = queryInput.trim();
    setQuery(next);
    if (next) {
      setLoading(true);
      setError(null);
    }
  }, [queryInput]);

  const wasteTypeDisplay = useMemo(() => {
    const first = rows[0];
    if (!first) {
      return EM_DASH;
    }
    return formatWasteTypeDisplay(first.waste_type_name);
  }, [rows]);

  useEffect(() => {
    void fetchRegistryCacheMetaResult().then((res) => {
      setCacheMetaReady(true);
      if (res.ok) {
        setCacheMeta(res.cache);
        setRegistryMetaError(null);
      } else {
        setCacheMeta(null);
        setRegistryMetaError(
          res.reason === "таймаут"
            ? "сервер не ответил вовремя"
            : res.reason === "сеть или CORS"
              ? "нет связи с API (сеть или CORS)"
              : `ответ сервера: ${res.reason}`,
        );
      }
    });
  }, []);

  useEffect(() => {
    void runSearch();
  }, [runSearch]);

  useEffect(() => {
    if (lat != null && lon != null) void refreshAddress(lat, lon);
    else setAddressLabel("");
  }, [lat, lon, refreshAddress]);

  const handleRegistryFiles = useCallback(
    async (list: FileList | null) => {
      if (!list?.length) return;
      const files = Array.from(list).filter((f) => f.name.toLowerCase().endsWith(".pdf"));
      if (!files.length) {
        setImportError("Выберите файлы в формате PDF.");
        return;
      }
      setImportError(null);
      setImportBusy(true);
      setImportProgress(0);
      setImportMessage("Подготовка загрузки…");
      try {
        const total = files.length;
        for (let i = 0; i < total; i += 1) {
          const file = files[i];
          const base = Math.round((i / total) * 100);
          const span = Math.max(1, Math.round(100 / total));
          const progressForFile = (pctInFile: number) =>
            Math.min(100, Math.round(base + (pctInFile / 100) * span));
          const prefix = total > 1 ? `Файл ${i + 1}/${total}: ${file.name}. ` : "";

          setImportMessage(`${prefix}Отправка на сервер…`);
          setImportMetrics(null);
          const post = await postRegistryImportWithUploadProgress([file], (up) => {
            setImportProgress(progressForFile(Math.min(35, Math.round(up * 0.35))));
            setImportMessage(`${prefix}Отправка на сервер…`);
          });

          if (post.skipped) {
            if (post.cache) {
              setCacheMeta(post.cache);
              setRegistryMetaError(null);
              setCacheMetaReady(true);
            } else {
              const res = await fetchRegistryCacheMetaResult();
              setCacheMetaReady(true);
              if (res.ok) {
                setCacheMeta(res.cache);
                setRegistryMetaError(null);
              } else {
                setCacheMeta(null);
                setRegistryMetaError(res.reason);
              }
            }
            setImportMessage(prefix + (post.message || "Данные совпадают с кэшем — импорт пропущен."));
            setImportProgress(Math.min(100, base + span));
          } else {
            let transientStatusFails = 0;
            for (;;) {
              let st;
              try {
                st = await fetchRegistryImportStatus(post.job_id);
                transientStatusFails = 0;
              } catch (statusErr) {
                const msg =
                  statusErr instanceof Error && statusErr.message
                    ? statusErr.message
                    : String(statusErr || "");
                const transient =
                  /(?:\b502\b|\b503\b|\b504\b|timeout|timed out|fetch|network|сеть)/i.test(msg);
                if (transient && transientStatusFails < 25) {
                  transientStatusFails += 1;
                  setImportMessage(prefix + "Связь с API прервалась, ждём восстановление…");
                  await new Promise((r) => setTimeout(r, 700));
                  continue;
                }
                throw statusErr;
              }

              setImportMessage(prefix + (st.message || st.status));
              setImportMetrics(st.metrics ?? null);
              setImportProgress(progressForFile(Math.min(100, Math.round(35 + st.progress * 0.65))));
              if (st.status === "done") break;
              if (st.status === "error") {
                const detail =
                  (st.message && st.message.trim()) ||
                  st.error ||
                  "Ошибка обработки реестра";
                throw new Error(detail);
              }
              await new Promise((r) => setTimeout(r, 450));
            }

            const res = await fetchRegistryCacheMetaResult();
            setCacheMetaReady(true);
            if (res.ok) {
              setCacheMeta(res.cache);
              setRegistryMetaError(null);
            } else {
              setCacheMeta(null);
              setRegistryMetaError(res.reason);
            }
            setImportMessage(total > 1 ? `Файл ${i + 1}/${total} обработан.` : "Готово. Обновляем список…");
            setImportProgress(Math.min(100, base + span));
          }
        }
        setImportMessage("Готово. Обновляем список…");
        setImportProgress(100);
        await runSearch();
      } catch (e) {
        const msg =
          e instanceof Error && e.message
            ? e.message
            : "Ошибка загрузки";
        setImportError(msg);
      } finally {
        setImportBusy(false);
        setImportProgress(0);
        setImportMessage("");
        setImportMetrics(null);
        if (fileRef.current) fileRef.current.value = "";
      }
    },
    [runSearch],
  );

  const hasActiveQuery = query.trim().length > 0;
  const showSearchLoader = loading && !importBusy && (hasActiveQuery || queryInput.trim().length > 0);
  const showSkeleton = hasActiveQuery && (loading || importBusy);

  const locationChosen = lat != null && lon != null;
  const showDistanceSearchLoader = loading && locationChosen && !importBusy;
  const locationDisplay = locationChosen
    ? addressLabel.trim() || `${lat!.toFixed(4)}, ${lon!.toFixed(4)}`
    : LOCATION_PLACEHOLDER;

  const registryLoaded = Boolean(cacheMeta && cacheMeta.record_count > 0);
  const registryUploadedAt = useMemo(() => {
    if (!cacheMeta?.updated_at) return null;
    try {
      return new Date(cacheMeta.updated_at).toLocaleString("ru-BY", {
        day: "numeric",
        month: "long",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return cacheMeta.updated_at;
    }
  }, [cacheMeta?.updated_at]);

  return (
    <div className="relative z-10 mx-auto flex w-full max-w-[min(100%,96rem)] flex-col gap-8 py-10 pr-4 pl-8 sm:pr-6 sm:pl-12 md:pl-14">
      <div className="relative z-10 flex flex-wrap items-center justify-end gap-2 pl-10 text-sm sm:pl-16 md:pl-24 lg:pl-28">
        <span className="mr-auto min-w-0 text-emerald-900/70">
          {user?.name ? (
            <>
              <span className="font-medium text-emerald-950">{user.name}</span>
              <span className="text-emerald-800/60"> · {user.email}</span>
            </>
          ) : null}
        </span>
        {user?.role === "admin" ? (
          <Link
            href="/admin"
            className="rounded-xl border border-emerald-200/90 bg-white px-3 py-2 font-medium text-emerald-900 shadow-sm transition hover:bg-emerald-50/90"
          >
            Админ-панель
          </Link>
        ) : null}
        <button
          type="button"
          onClick={() => {
            void (async () => {
              await logout();
              window.location.href = "/";
            })();
          }}
          className="rounded-xl border border-stone-200 bg-white px-3 py-2 font-medium text-stone-700 transition hover:bg-stone-50"
        >
          Выйти
        </button>
      </div>

      <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight text-emerald-950">
            Поиск объектов обращения с отходами
          </h1>
          <p className="text-sm text-emerald-900/55">
            {canImportRegistry
              ? "Загрузите PDF реестров (часть I и II) — данные кэшируются на сервере. "
              : "Данные реестра на сервере. "}
            В списке — семь ближайших объектов к выбранной точке. Показываем два расчёта: по воздуху (Haversine) и по
            дорогам (OSRM, с fallback при недоступности роутинга). Обе дистанции оценочные; рядом выводится примерный
            разброс (± км). Карта — OpenStreetMap.
          </p>
          <div className="flex flex-col gap-1 border-l-2 border-emerald-200/80 py-0.5 pl-3 text-xs sm:text-[13px]">
            <p className="text-emerald-900/80">
              <span className="font-semibold text-emerald-950">Реестр в системе:</span>{" "}
              {!cacheMetaReady ? (
                <span className="text-emerald-800/50">проверка…</span>
              ) : registryMetaError ? (
                <span className="text-red-800/95" title={registryMetaError}>
                  статус неизвестен
                </span>
              ) : registryLoaded ? (
                <span className="text-emerald-800">загружен</span>
              ) : (
                <span className="text-amber-800/90">не загружен</span>
              )}
            </p>
            <p className="text-emerald-900/80">
              <span className="font-semibold text-emerald-950">Дата загрузки / обновления:</span>{" "}
              {!cacheMetaReady ? (
                <span className="text-emerald-800/50">—</span>
              ) : registryMetaError ? (
                <span className="text-emerald-800/50">—</span>
              ) : registryLoaded && registryUploadedAt ? (
                <span className="text-emerald-800">{registryUploadedAt}</span>
              ) : (
                <span className="text-emerald-800/55">—</span>
              )}
            </p>
            {registryMetaError && cacheMetaReady ? (
              <p className="text-xs text-red-800/90">
                Не удалось запросить <code className="rounded bg-red-100/80 px-1">/api/v1/registry/cache</code>:{" "}
                {registryMetaError}. Запустите API и edge (nginx), проверьте{" "}
                <code className="rounded bg-red-100/80 px-1">NEXT_PUBLIC_API_URL</code> (в Docker — относительные{" "}
                <code className="rounded bg-red-100/80 px-1">/api/...</code>).
              </p>
            ) : null}
            {registryLoaded && cacheMeta ? (
              <>
                <p className="text-emerald-800/50">
                  В кэше записей:{" "}
                  <span className="font-medium tabular-nums text-emerald-900/70">{cacheMeta.record_count}</span>
                </p>
                <p className="text-emerald-800/50">
                  Принимают от других:{" "}
                  <span className="font-medium tabular-nums text-emerald-900/70">
                    {cacheMeta.accepts_true_count ?? "—"}
                  </span>
                </p>
                <p className="text-emerald-800/50">
                  Не принимают от других:{" "}
                  <span className="font-medium tabular-nums text-emerald-900/70">
                    {cacheMeta.accepts_false_count ?? "—"}
                  </span>
                </p>
              </>
            ) : cacheMetaReady && !registryMetaError && !registryLoaded ? (
              canImportRegistry ? (
                <p className="text-amber-800/85">
                  Нажмите «Загрузить реестр» и выберите один или два PDF с ecoinfo.by.
                </p>
              ) : (
                <p className="text-amber-800/85">
                  Реестр ещё не загружен в систему. Обратитесь к администратору для загрузки PDF.
                </p>
              )
            ) : null}
          </div>
        </div>
        {canImportRegistry ? (
          <div className="flex shrink-0 flex-col gap-2 sm:items-end">
            <input
              ref={fileRef}
              type="file"
              accept="application/pdf,.pdf"
              multiple
              className="hidden"
              onChange={(e) => void handleRegistryFiles(e.target.files)}
            />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={importBusy}
              className="rounded-2xl border border-emerald-200/90 bg-white px-4 py-2.5 text-sm font-medium text-emerald-950 shadow-sm shadow-emerald-900/5 transition hover:border-emerald-300 hover:bg-emerald-50/80 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {importBusy ? "Обработка…" : "Загрузить реестр"}
            </button>
          </div>
        ) : null}
      </header>

      {importError ? (
        <p className="rounded-xl border border-red-200/90 bg-red-50/95 px-4 py-3 text-sm text-red-800">{importError}</p>
      ) : null}

      {importBusy ? (
        <div
          className="rounded-2xl border border-emerald-200/80 bg-emerald-50/90 px-4 py-4 shadow-sm shadow-emerald-900/5"
          role="status"
          aria-live="polite"
        >
          <p className="mb-3 text-sm font-medium text-emerald-950">{importMessage || "Обработка…"}</p>
          <div className="h-2.5 w-full overflow-hidden rounded-full bg-emerald-100">
            <div
              className="h-full rounded-full bg-emerald-500 transition-[width] duration-300 ease-out"
              style={{ width: `${importProgress}%` }}
            />
          </div>
          {importMetrics ? (
            <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] leading-snug text-emerald-900/75 sm:grid-cols-4">
              <span className="rounded-lg bg-emerald-100/80 px-2 py-1">
                Скорость: <b>{importMetrics.rows_per_sec ?? EM_DASH}</b>/с
              </span>
              <span className="rounded-lg bg-emerald-100/80 px-2 py-1">
                ETA: <b>{formatEta(importMetrics.eta_sec)}</b>
              </span>
              <span className="rounded-lg bg-emerald-100/80 px-2 py-1">
                Nominatim: <b>{importMetrics.nominatim_calls ?? 0}</b>
              </span>
              <span className="rounded-lg bg-emerald-100/80 px-2 py-1">
                Кэш/approx: <b>{(importMetrics.cache_hit ?? 0) + (importMetrics.approx_hit ?? 0)}</b>
              </span>
            </div>
          ) : null}
          <p className="mt-2 text-xs text-emerald-900/50">
            {/\bстраница\s+\d+/i.test(importMessage) ? (
              <>
                Сейчас на сервере извлекается текст из PDF (это ещё не геокодирование). Очень большие части II
                идут долго; если номер страницы долго не меняется — часто «тяжёлая» страница или режим pdfplumber.
                Убедитесь, что API собран с PyMuPDF по умолчанию и в{" "}
                <code className="rounded bg-emerald-100/80 px-1">REGISTRY_PDF_TEXT_BACKEND</code> не задано{" "}
                <code className="rounded bg-emerald-100/80 px-1">pdfplumber</code>.
              </>
            ) : (
              <>
                Геокодирование адресов идёт через Nominatim и может занять несколько минут при первой загрузке
                (этап «Геокодирование: …» в сообщении выше).
              </>
            )}
          </p>
        </div>
      ) : null}

      <section className="flex flex-col gap-5">
        <div className="flex flex-col gap-2">
          <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-stretch">
            <label className="min-w-0 flex-1">
              <span className="sr-only">
                Код объекта или вид отхода — строка поиска
              </span>
              <input
                type="search"
                value={queryInput}
                onChange={(e) => {
                  setQueryInput(e.target.value);
                  setLat(undefined);
                  setLon(undefined);
                  setAddressLabel("");
                }}
                onKeyDown={(e) => e.key === "Enter" && submitQuery()}
                placeholder="Код объекта или вид отхода"
                disabled={importBusy}
                className="h-full w-full min-h-[3rem] rounded-2xl border border-emerald-100 bg-white/90 px-5 py-3.5 text-base text-stone-800 shadow-inner shadow-emerald-900/5 outline-none ring-emerald-200/60 placeholder:text-emerald-900/35 focus:border-emerald-300 focus:ring-2 disabled:opacity-60"
              />
            </label>
            <button
              type="button"
              onClick={() => submitQuery()}
              disabled={loading || importBusy}
              className="shrink-0 rounded-2xl bg-emerald-700 px-6 py-3.5 text-base font-medium text-white shadow-sm shadow-emerald-900/20 transition hover:bg-emerald-800 disabled:opacity-60 sm:min-w-[8.5rem]"
            >
              {loading ? (locationChosen ? "Расчёт…" : "Загрузка…") : "Найти"}
            </button>
          </div>
          {showSearchLoader ? (
            <p
              className="inline-flex items-center gap-2 text-xs text-emerald-900/75"
              role="status"
              aria-live="polite"
            >
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-emerald-600" aria-hidden />
              Загружаем данные по запросу…
            </p>
          ) : null}
          {error ? (
            <p className="text-sm text-red-600">
              {error}
              {typeof error === "string" && error.includes("docker compose") ? null : (
                <> Локальная разработка: API на порту 8000; Docker: проверьте контейнеры и nginx.</>
              )}
            </p>
          ) : null}
        </div>

        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <WasteTypeField value={wasteTypeDisplay} />

          <div className="flex w-full flex-col gap-2 lg:w-80">
            <span className="text-xs font-medium uppercase tracking-wide text-emerald-800/50">
              Местоположение объекта
            </span>
            <div
              className={`rounded-2xl border border-emerald-100/80 bg-emerald-50/80 px-4 py-3 text-sm leading-snug shadow-sm shadow-emerald-900/5 min-h-[3.25rem] flex items-center ${
                locationChosen ? "text-stone-800" : "text-emerald-800/40 italic"
              }`}
            >
              {locationDisplay}
            </div>
            <button
              type="button"
              onClick={() => setMapOpen(true)}
              disabled={importBusy}
              className="rounded-2xl border border-emerald-200/90 bg-emerald-600 px-4 py-3 text-center text-sm font-medium text-white shadow-sm shadow-emerald-900/15 transition hover:border-emerald-300 hover:bg-emerald-700 disabled:opacity-60"
            >
              Выбрать местоположение
            </button>
            {!locationChosen ? (
              <p className="text-[11px] leading-snug text-emerald-800/55">
                После выбора точки на карте появится ориентировочное расстояние до объектов по их адресам.
              </p>
            ) : null}
          </div>
        </div>
      </section>

      <section className="space-y-3">
        {hasActiveQuery ? (
          <div
            className={`hidden gap-3 px-3 text-[10px] font-semibold uppercase tracking-wide text-emerald-800/70 sm:grid sm:gap-x-5 sm:gap-y-2 ${RESULT_GRID}`}
          >
            <span>Код объекта</span>
            <span>Собственник</span>
            <span>Объект</span>
            <span>Адрес</span>
            <span>Телефоны</span>
            <span
              className="text-right normal-case sm:text-right"
              title="Расстояние по прямой (Haversine)"
            >
              По воздуху, км
            </span>
            <span
              className="text-right normal-case sm:text-right"
              title="Расстояние по дорогам (OSRM)"
            >
              По дорогам, км
            </span>
          </div>
        ) : null}

        {hasActiveQuery && showSkeleton ? (
          <ResultsSkeleton />
        ) : hasActiveQuery ? (
          <>
            {locationChosen && query.trim() ? (
              <p className="rounded-xl border border-emerald-100/80 bg-emerald-50/60 px-3 py-2 text-xs leading-snug text-emerald-900/85">
                С выбранной точкой на карте в список попадают только объекты, которые принимают
                отходы от других. Полный перечень объектов хранится в базе после импорта PDF.
              </p>
            ) : null}
            <ul className="flex flex-col gap-4">
            {rows.map((row, idx) => (
              <li
                key={`${row.waste_code ?? "x"}-${row.id}-${idx}`}
                className={`grid grid-cols-1 gap-3 rounded-2xl border border-emerald-100/90 bg-white/95 p-3 shadow-sm shadow-emerald-900/5 ${RESULT_GRID} sm:items-start sm:gap-x-5 sm:gap-y-3`}
              >
                <CodeCell row={row} />
                <OwnerCell row={row} />
                <ObjectCell row={row} />
                <AddressCell row={row} />
                <PhonesCell row={row} />
                <AirDistanceCell
                  row={row}
                  locationChosen={locationChosen}
                  distanceNotCalculatedNote={DISTANCE_NOT_CALCULATED_NOTE}
                />
                <RoadDistanceCell
                  row={row}
                  locationChosen={locationChosen}
                  roadDistanceNotCalculatedNote={ROAD_DISTANCE_NOT_CALCULATED_NOTE}
                />
              </li>
            ))}
          </ul>
          </>
        ) : (
          <p className="text-center text-xs text-emerald-900/55">
            Выберите код объекта или вид отхода, затем нажмите «Найти».
          </p>
        )}

        {hasActiveQuery && !showSkeleton && rows.length === 0 && !error ? (
          <p className="text-center text-xs text-emerald-900/45">
            Нет данных: загрузите реестр PDF или измените запрос / точку на карте.
          </p>
        ) : null}
      </section>

      <LocationMapModal
        open={mapOpen}
        onClose={() => setMapOpen(false)}
        initialLat={lat}
        initialLon={lon}
        onConfirm={(la, lo) => {
          setLat(la);
          setLon(lo);
          setMapOpen(false);
        }}
      />
      {showDistanceSearchLoader ? (
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-emerald-950/35 px-4 py-6 backdrop-blur-[1.5px]">
          <DistanceCalculationLoader />
        </div>
      ) : null}
    </div>
  );
}
