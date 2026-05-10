"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { fetchRegistryCacheMetaResult, type RegistryCacheMeta } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { Button, linkAsButtonSecondaryClass } from "@/components/ui/Button";
import {
  AddressCell,
  AirDistanceCell,
  CodeCell,
  ObjectCell,
  OwnerCell,
  PhonesCell,
  RoadDistanceCell,
} from "./resultCells";
import { useRegistryImport } from "./hooks/useRegistryImport";
import { useSearch } from "./hooks/useSearch";
import { useWasteSuggest } from "./hooks/useWasteSuggest";
import { RegistryImportPanel } from "./RegistryImportPanel";

const LocationMapModal = dynamic(
  () => import("./LocationMapModal").then((m) => m.LocationMapModal),
  { ssr: false },
);

const LOCATION_PLACEHOLDER = "Выберите местоположение объекта";

/** Сетка строки результатов: код | собственник | объект | адрес | телефоны | по воздуху | по дорогам */
const RESULT_GRID =
  "sm:grid-cols-[minmax(5rem,5.5rem)_minmax(14.2rem,1.15fr)_minmax(14.2rem,1.15fr)_minmax(16.2rem,1.4fr)_minmax(10.1rem,0.95fr)_minmax(calc(7.4rem_-_10px),0.8fr)_minmax(calc(7.4rem_-_10px),0.8fr)]";

/** Под строкой с «—», если точка на карте выбрана, а км не посчитались */
const DISTANCE_NOT_CALCULATED_NOTE = "Расстояние не удалось рассчитать";
const ROAD_DISTANCE_NOT_CALCULATED_NOTE = "По дорогам: расчёт не выполнен";

function ResultsSkeleton() {
  return (
    <ul className="flex flex-col gap-4" aria-hidden>
      {Array.from({ length: 7 }).map((_, i) => (
        <li
          key={i}
          className={`grid animate-pulse grid-cols-1 gap-3 rounded-2xl border border-emerald-100/90 bg-white/90 p-4 shadow-sm shadow-emerald-900/5 ${RESULT_GRID} sm:items-stretch sm:gap-x-5 sm:gap-y-3`}
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
  const [importBusy, setImportBusy] = useState(false);
  const [cacheMeta, setCacheMeta] = useState<RegistryCacheMeta | null>(null);
  const [cacheMetaReady, setCacheMetaReady] = useState(false);
  const [registryMetaError, setRegistryMetaError] = useState<string | null>(null);
  const [serverRegistryImportInProgress, setServerRegistryImportInProgress] = useState(false);

  const onCacheMetaUpdate = useCallback(
    (meta: RegistryCacheMeta | null, ready: boolean, err: string | null, serverImport?: boolean) => {
      setCacheMetaReady(ready);
      if (err != null) {
        setCacheMeta(null);
        setServerRegistryImportInProgress(false);
        setRegistryMetaError(
          err === "таймаут"
            ? "сервер не ответил вовремя"
            : err === "сеть или CORS"
              ? "нет связи с API (сеть или CORS)"
              : `ответ сервера: ${err}`,
        );
        return;
      }
      setCacheMeta(meta);
      setRegistryMetaError(null);
      if (serverImport !== undefined) {
        setServerRegistryImportInProgress(serverImport);
      }
    },
    [],
  );

  useEffect(() => {
    void fetchRegistryCacheMetaResult().then((res) => {
      if (res.ok) {
        onCacheMetaUpdate(res.cache, true, null, res.registry_import_in_progress);
      } else {
        onCacheMetaUpdate(null, true, res.reason);
      }
    });
  }, [onCacheMetaUpdate]);

  useEffect(() => {
    if (canImportRegistry || !serverRegistryImportInProgress) return;
    const id = window.setInterval(() => {
      void fetchRegistryCacheMetaResult().then((res) => {
        if (res.ok) {
          onCacheMetaUpdate(res.cache, true, null, res.registry_import_in_progress);
        }
      });
    }, 10_000);
    return () => window.clearInterval(id);
  }, [canImportRegistry, serverRegistryImportInProgress, onCacheMetaUpdate]);

  const search = useSearch(importBusy);

  const reg = useRegistryImport({
    importBusy,
    setImportBusy,
    abortSearch: search.abortSearch,
    runSearch: search.runSearch,
    setLoading: search.setLoading,
    onCacheMetaUpdate,
  });

  const waste = useWasteSuggest({
    queryInput: search.queryInput,
    setQueryInput: search.setQueryInput,
    importBusy,
    commitQuery: search.commitQuery,
  });

  const {
    queryInput,
    setQueryInput,
    query,
    lat,
    lon,
    setLat,
    setLon,
    addressLabel,
    mapOpen,
    setMapOpen,
    rows,
    loading,
    error,
    submitQuery,
    hasActiveQuery,
    showSearchLoader,
    showSkeleton,
    showDistanceSearchLoader,
    locationChosen,
  } = search;

  const {
    wasteSuggest,
    showWasteSuggest,
    setShowWasteSuggest,
    wasteSuggestActive,
    setWasteSuggestActive,
    suggestionLabel,
    applySuggestion,
    renderHighlightedLabel,
  } = waste;

  const {
    fileRef,
    importProgress,
    importMessage,
    importError,
    importMetrics,
    uploadEtaSec,
    uploadSpeedMbps,
    uploadPhase,
    importElapsedSec,
    totalEtaSec,
    importTimeline,
    handleRegistryFiles,
  } = reg;

  const locationDisplay = locationChosen
    ? addressLabel.trim() || `${lat!.toFixed(4)}, ${lon!.toFixed(4)}`
    : LOCATION_PLACEHOLDER;

  const registryLoaded = Boolean(cacheMeta && cacheMeta.record_count > 0);
  const showAdminImportNotice = !canImportRegistry && serverRegistryImportInProgress;
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
    <div className="relative z-10 mx-auto flex w-full max-w-[min(100%,96rem)] flex-col gap-8 px-5 py-8 sm:px-8 sm:py-10 md:px-10">
      <Card
        padding="none"
        className="relative z-10 ms-auto flex w-fit max-w-full min-w-0 flex-wrap items-center justify-end gap-x-3 gap-y-2 px-4 py-3 text-sm shadow-sm"
      >
        <span className="min-w-0 shrink text-right text-emerald-900/75">
          {user?.name ? (
            <>
              <span className="font-semibold text-emerald-950">{user.name}</span>
              <span className="font-normal text-emerald-800/55"> · {user.email}</span>
            </>
          ) : null}
        </span>
        {user?.role === "admin" ? (
          <Link href="/admin" className={linkAsButtonSecondaryClass}>
            Админ-панель
          </Link>
        ) : null}
        <Button
          type="button"
          variant="ghost"
          size="md"
          onClick={() => {
            void (async () => {
              await logout();
              window.location.href = "/";
            })();
          }}
        >
          Выйти
        </Button>
      </Card>

      <header className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
        <div className="max-w-3xl space-y-3">
          <h1 className="text-2xl font-semibold tracking-tight text-stone-900 sm:text-3xl">
            Поиск объектов обращения с отходами
          </h1>
          <p className="text-sm leading-relaxed text-stone-700 sm:text-[15px]">
            {canImportRegistry
              ? "Загрузите PDF реестров (часть I и II) — данные кэшируются на сервере. "
              : "Данные реестра на сервере. "}
            В списке — семь ближайших объектов к выбранной точке. Показываем два расчёта: по воздуху (Haversine) и по
            дорогам (OSRM, с fallback при недоступности роутинга). Обе дистанции оценочные; рядом выводится примерный
            разброс (± км). Карта — OpenStreetMap.
          </p>
          <div className="flex flex-col gap-2 rounded-2xl border border-emerald-100/90 bg-white/70 p-4 text-xs leading-relaxed shadow-sm shadow-emerald-950/[0.03] sm:text-[13px]">
            {showAdminImportNotice ? (
              <p className="rounded-xl border border-amber-200/90 bg-amber-50/95 px-3 py-2 text-[13px] font-medium text-amber-950 sm:text-sm">
                Администратор обновляет реестр — данные на сервере могут меняться. Подождите завершения импорта.
              </p>
            ) : null}
            <p className="text-stone-800">
              <span className="font-semibold text-stone-900">Реестр в системе:</span>{" "}
              {!cacheMetaReady ? (
                <span className="text-stone-600">проверка…</span>
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
            <p className="text-stone-800">
              <span className="font-semibold text-stone-900">Дата загрузки / обновления:</span>{" "}
              {!cacheMetaReady ? (
                <span className="text-stone-600">—</span>
              ) : registryMetaError ? (
                <span className="text-stone-600">—</span>
              ) : registryLoaded && registryUploadedAt ? (
                <span className="text-stone-800">{registryUploadedAt}</span>
              ) : (
                <span className="text-stone-600">—</span>
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
                <p className="text-stone-600">
                  В кэше записей:{" "}
                  <span className="font-medium tabular-nums text-stone-800">
                    {cacheMeta.record_count}
                  </span>
                </p>
                <p className="text-stone-600">
                  Принимают от других:{" "}
                  <span className="font-medium tabular-nums text-stone-800">
                    {cacheMeta.accepts_true_count ?? "—"}
                  </span>
                </p>
                <p className="text-stone-600">
                  Не принимают от других:{" "}
                  <span className="font-medium tabular-nums text-stone-800">
                    {cacheMeta.accepts_false_count ?? "—"}
                  </span>
                </p>
                <p className="text-stone-600">
                  Не определено (приём от других):{" "}
                  <span className="font-medium tabular-nums text-stone-800">
                    {cacheMeta.accepts_unknown_count ?? "—"}
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
          <div className="flex shrink-0 flex-col gap-2 sm:items-end sm:pt-1">
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,.webp,.bmp,.tif,.tiff,.html,.htm,.txt,application/pdf,image/jpeg,image/png,image/webp,text/html,text/plain"
              multiple
              className="hidden"
              onChange={(e) => void handleRegistryFiles(e.target.files)}
            />
            <Button
              type="button"
              variant="primary"
              size="lg"
              onClick={() => fileRef.current?.click()}
              disabled={importBusy}
            >
              {importBusy ? "Обработка…" : "Загрузить реестр"}
            </Button>
          </div>
        ) : null}
      </header>

      <RegistryImportPanel
        importError={importError}
        importBusy={importBusy}
        importMessage={importMessage}
        importProgress={importProgress}
        importMetrics={importMetrics}
        importTimeline={importTimeline}
        uploadEtaSec={uploadEtaSec}
        uploadSpeedMbps={uploadSpeedMbps}
        uploadPhase={uploadPhase}
        importElapsedSec={importElapsedSec}
        totalEtaSec={totalEtaSec}
      />

      <section className="flex flex-col gap-4">
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,28rem)] lg:items-stretch lg:gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 max-w-4xl flex-col gap-2.5 sm:flex-row sm:items-stretch">
            <label className="relative min-w-0 sm:flex-1">
              <span className="sr-only">
                Код отхода или вид отхода — строка поиска
              </span>
              <input
                type="search"
                value={queryInput}
                onChange={(e) => {
                  setQueryInput(e.target.value);
                  setShowWasteSuggest(true);
                  setWasteSuggestActive(0);
                }}
                onBlur={() => {
                  setTimeout(() => setShowWasteSuggest(false), 120);
                }}
                onFocus={() => {
                  if (wasteSuggest.length > 0) {
                    setShowWasteSuggest(true);
                    if (wasteSuggestActive < 0) setWasteSuggestActive(0);
                  }
                }}
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    setShowWasteSuggest(false);
                    setWasteSuggestActive(-1);
                    return;
                  }
                  if (showWasteSuggest && wasteSuggest.length > 0 && e.key === "ArrowDown") {
                    e.preventDefault();
                    setWasteSuggestActive((prev) => {
                      const base = prev < 0 ? 0 : prev;
                      return Math.min(wasteSuggest.length - 1, base + 1);
                    });
                    return;
                  }
                  if (showWasteSuggest && wasteSuggest.length > 0 && e.key === "ArrowUp") {
                    e.preventDefault();
                    setWasteSuggestActive((prev) => {
                      const base = prev < 0 ? 0 : prev;
                      return Math.max(0, base - 1);
                    });
                    return;
                  }
                  if (e.key === "Enter") {
                    if (showWasteSuggest && wasteSuggest.length > 0) {
                      const idx = wasteSuggestActive >= 0 ? wasteSuggestActive : 0;
                      const picked = wasteSuggest[Math.max(0, Math.min(wasteSuggest.length - 1, idx))];
                      if (picked) {
                        applySuggestion(picked);
                        return;
                      }
                    }
                    submitQuery();
                  }
                }}
                placeholder="Код отхода или вид отхода"
                disabled={importBusy}
                className="h-full w-full min-h-[2.85rem] rounded-2xl border border-emerald-200/70 bg-white px-4 py-3 text-[15px] text-stone-800 shadow-sm shadow-emerald-950/[0.04] outline-none ring-emerald-200/50 placeholder:text-stone-500 focus:border-emerald-400/80 focus:ring-2 focus:ring-emerald-300/50 disabled:opacity-60"
              />
              {showWasteSuggest && wasteSuggest.length > 0 ? (
                <div className="absolute z-30 mt-1 w-full overflow-hidden rounded-xl border border-emerald-200/80 bg-white shadow-lg shadow-emerald-900/10">
                  <ul className="max-h-72 overflow-auto py-1 text-sm">
                    {wasteSuggest.map((it, i) => {
                      const label = suggestionLabel(it);
                      const active = i === wasteSuggestActive;
                      return (
                        <li key={`${it.waste_code}-${i}`}>
                          <button
                            type="button"
                            onMouseDown={(e) => e.preventDefault()}
                            onMouseEnter={() => setWasteSuggestActive(i)}
                            onClick={() => applySuggestion(it)}
                            className={`w-full px-3 py-2 text-left text-emerald-950 hover:bg-emerald-50 ${
                              active ? "bg-emerald-50" : ""
                            }`}
                          >
                            {renderHighlightedLabel(label, queryInput)}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ) : null}
            </label>
            <Button
              type="button"
              variant="primary"
              size="lg"
              onClick={() => submitQuery()}
              disabled={loading || importBusy}
              className="min-h-[2.85rem] sm:min-w-[8rem] sm:self-auto lg:min-w-[8.5rem]"
            >
              {loading ? (locationChosen ? "Расчёт…" : "Загрузка…") : "Найти"}
            </Button>
            </div>
            {showSearchLoader ? (
              <p
                className="mt-2 inline-flex items-center gap-2 text-xs text-emerald-900/75"
                role="status"
                aria-live="polite"
              >
                <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-emerald-600" aria-hidden />
                Загружаем данные по запросу…
              </p>
            ) : null}
            <p className="mt-1 text-[11px] text-stone-600">
              Поиск выполняется только по коду отхода и виду отхода.
            </p>
            {error ? (
              <p className="mt-1 text-sm text-red-600">
                {error}
                {typeof error === "string" && error.includes("docker compose") ? null : (
                  <> Локальная разработка: API на порту 8000; Docker: проверьте контейнеры и nginx.</>
                )}
              </p>
            ) : null}
          </div>

          <div className="box-border flex w-full max-w-full min-w-0 flex-col rounded-2xl border border-emerald-200/60 bg-white p-4 shadow-sm shadow-emerald-950/[0.05] sm:p-5 lg:h-full lg:min-h-0 lg:justify-center">
            <div className="flex w-full min-w-0 min-h-[3rem] flex-col gap-3 sm:flex-row sm:items-stretch">
              <div
                className={`flex min-h-[3rem] min-w-0 flex-1 basis-0 items-center rounded-2xl border px-3 py-3 text-[13px] leading-snug shadow-sm sm:px-4 ${
                  locationChosen
                    ? "border-emerald-200/70 bg-emerald-50/90 text-stone-800 shadow-emerald-950/[0.04]"
                    : "border-emerald-100/80 bg-emerald-50/50 text-stone-700 italic shadow-emerald-900/[0.03]"
                }`}
              >
                {locationDisplay}
              </div>
              <Button
                type="button"
                variant="primary"
                size="lg"
                onClick={() => setMapOpen(true)}
                disabled={importBusy}
                className="min-h-[3rem] w-full min-w-0 flex-1 basis-0 self-stretch whitespace-normal px-3 text-center text-[13px] leading-snug sm:px-4"
              >
                Выбрать местоположение
              </Button>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3">
        {hasActiveQuery ? (
          <div
            className={`hidden gap-3 px-3 text-[11px] font-semibold uppercase tracking-wide text-stone-700 sm:grid sm:items-stretch sm:gap-x-5 sm:gap-y-2 ${RESULT_GRID}`}
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
                className={`grid grid-cols-1 gap-3 rounded-2xl border border-emerald-200/55 bg-white p-4 shadow-md shadow-emerald-950/[0.06] ${RESULT_GRID} sm:items-stretch sm:gap-x-5 sm:gap-y-3`}
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
          <p className="text-center text-xs text-stone-600">
            Выберите код отхода или вид отхода, затем нажмите «Найти».
          </p>
        )}

        {hasActiveQuery && !showSkeleton && rows.length === 0 && !error ? (
          <p className="text-center text-xs text-stone-600">
            {registryLoaded
              ? "По этому запросу ничего не найдено. Уточните код или вид отхода."
              : "Нет данных: загрузите реестр PDF или измените запрос / точку на карте."}
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
