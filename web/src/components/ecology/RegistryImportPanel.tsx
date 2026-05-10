"use client";

import type { RegistryImportStatus } from "@/lib/api";
import { formatEta, formatImportStage } from "./explorerUtils";

export type RegistryImportPanelProps = {
  importError: string | null;
  importBusy: boolean;
  importMessage: string;
  importProgress: number;
  importMetrics: RegistryImportStatus["metrics"] | null;
  importTimeline: { done: Set<string>; current: string };
  uploadEtaSec: number | null;
  uploadSpeedMbps: number | null;
  uploadPhase: "uploading" | "waiting_server";
  importElapsedSec: number;
  totalEtaSec: number | null;
};

export function RegistryImportPanel({
  importError,
  importBusy,
  importMessage,
  importProgress,
  importMetrics,
  importTimeline,
  uploadEtaSec,
  uploadSpeedMbps,
  uploadPhase,
  importElapsedSec,
  totalEtaSec,
}: RegistryImportPanelProps) {
  return (
    <>
      {importError ? (
        <p className="rounded-xl border border-red-200/90 bg-red-50/95 px-4 py-3 text-sm text-red-800">
          {importError}
        </p>
      ) : null}

      {importBusy ? (
        <div
          className="rounded-2xl border border-emerald-200/80 bg-emerald-50/90 px-4 py-4 shadow-sm shadow-emerald-900/5"
          role="status"
          aria-live="polite"
        >
          <p className="mb-3 text-sm font-medium text-emerald-950">
            {importMessage || "Обработка…"}
          </p>
          <div className="h-2.5 w-full overflow-hidden rounded-full bg-emerald-100">
            <div
              className="h-full rounded-full bg-emerald-500 transition-[width] duration-300 ease-out"
              style={{ width: `${importProgress}%` }}
            />
          </div>
          {importMetrics ? (
            <div className="mt-2 space-y-2 text-[11px] leading-snug text-emerald-900/75">
              <div className="rounded-xl border border-emerald-200/70 bg-white/60 px-3 py-2">
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-emerald-800/70">
                  Этапы импорта
                </p>
                <ul className="space-y-1.5">
                  {(
                    [
                      ["queued", "Очередь задач"],
                      ["ocr", "OCR изображений"],
                      ["extract", "Извлечение текста"],
                      ["checkbox", "Чекбоксы в PDF"],
                      ["geocode", "Геокодирование"],
                    ] as const
                  ).map(([id, label]) => {
                    const isDone = importTimeline.done.has(id);
                    const isCurrent = importTimeline.current === id;
                    return (
                      <li key={id} className="flex items-center gap-2">
                        <span
                          className={`inline-block h-2.5 w-2.5 rounded-full ${
                            isDone
                              ? "bg-emerald-600"
                              : isCurrent
                                ? "animate-pulse bg-amber-500"
                                : "bg-emerald-200"
                          }`}
                        />
                        <span
                          className={`${
                            isDone
                              ? "text-emerald-900"
                              : isCurrent
                                ? "font-semibold text-emerald-950"
                                : "text-emerald-800/60"
                          }`}
                        >
                          {label}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              </div>

              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <span className="rounded-lg bg-emerald-100/80 text-emerald-950 px-2 py-1 sm:col-span-2">
                  Этап: <b>{formatImportStage(importMetrics.stage)}</b>
                </span>
                <span className="rounded-lg bg-emerald-100/80 text-emerald-950 px-2 py-1">
                  Общий прогресс: <b>{importProgress}%</b>
                </span>
                {importMetrics.stage_done != null && importMetrics.stage_total != null ? (
                  <span className="rounded-lg bg-emerald-100/80 text-emerald-950 px-2 py-1">
                    Прогресс этапа: <b>{importMetrics.stage_done}</b>/<b>{importMetrics.stage_total}</b>{" "}
                    {importMetrics.stage_unit ? <b>{importMetrics.stage_unit}</b> : null}
                  </span>
                ) : null}
                {importMetrics.stage_eta_sec != null ? (
                  <span className="rounded-lg bg-emerald-100/80 text-emerald-950 px-2 py-1">
                    ETA этапа: <b>{formatEta(importMetrics.stage_eta_sec)}</b>
                  </span>
                ) : null}
                {importElapsedSec > 0 ? (
                  <span className="rounded-lg bg-emerald-100/80 text-emerald-950 px-2 py-1">
                    Прошло: <b>{formatEta(importElapsedSec)}</b>
                  </span>
                ) : null}
                {uploadPhase === "uploading" && uploadEtaSec != null && importProgress <= 40 ? (
                  <span className="rounded-lg bg-amber-100/80 text-amber-950 px-2 py-1">
                    ETA загрузки: <b>{formatEta(uploadEtaSec)}</b>
                    {uploadSpeedMbps != null ? (
                      <>
                        , скорость: <b>{uploadSpeedMbps.toFixed(2)}</b> Mbps
                      </>
                    ) : null}
                  </span>
                ) : null}
                {uploadPhase === "waiting_server" && !importMetrics ? (
                  <span className="rounded-lg bg-amber-100/80 text-amber-950 px-2 py-1 sm:col-span-2">
                    Загрузка завершена, сервер обрабатывает multipart и готовит задачу импорта…
                  </span>
                ) : null}
                {totalEtaSec != null ? (
                  <span className="rounded-lg bg-amber-100/80 text-amber-950 px-2 py-1">
                    ETA всего (примерно): <b>{formatEta(totalEtaSec)}</b>
                  </span>
                ) : null}
                {importMetrics.queue_position != null ? (
                  <span className="rounded-lg bg-amber-100/80 text-amber-950 px-2 py-1">
                    Очередь: <b>{importMetrics.queue_position === 0 ? "в работе" : importMetrics.queue_position}</b>
                    {importMetrics.queue_size != null ? (
                      <>
                        {" "}
                        из <b>{importMetrics.queue_size}</b>
                      </>
                    ) : null}
                    {importMetrics.queue_eta_sec != null && importMetrics.queue_position > 0 ? (
                      <>
                        {" "}
                        (ожидание: <b>{formatEta(importMetrics.queue_eta_sec)}</b>)
                      </>
                    ) : null}
                  </span>
                ) : null}
                {importMetrics.file_name ? (
                  <span className="rounded-lg bg-emerald-100/80 text-emerald-950 px-2 py-1 sm:col-span-2">
                    Файл: <b>{importMetrics.file_index ?? "?"}</b>/<b>{importMetrics.files_total ?? "?"}</b> —{" "}
                    <b>{importMetrics.file_name}</b>
                  </span>
                ) : null}
                {importMetrics.page != null && importMetrics.pages_total != null ? (
                  <span className="rounded-lg bg-emerald-100/80 text-emerald-950 px-2 py-1">
                    Страница: <b>{importMetrics.page}</b>/<b>{importMetrics.pages_total}</b>
                  </span>
                ) : null}
                {importMetrics.files_done != null && importMetrics.files_total != null ? (
                  <span className="rounded-lg bg-emerald-100/80 text-emerald-950 px-2 py-1">
                    Файлов обработано: <b>{importMetrics.files_done}</b>/<b>{importMetrics.files_total}</b>
                  </span>
                ) : null}
                {importMetrics.ocr_total != null && importMetrics.ocr_total > 0 ? (
                  <span className="rounded-lg bg-amber-100/80 text-amber-950 px-2 py-1 sm:col-span-2">
                    OCR: <b>{importMetrics.ocr_done ?? 0}</b>/<b>{importMetrics.ocr_total}</b>
                    {importMetrics.ocr_inflight != null ? (
                      <>
                        , в работе: <b>{importMetrics.ocr_inflight}</b>
                      </>
                    ) : null}
                    {importMetrics.ocr_workers != null && importMetrics.ocr_workers > 0 ? (
                      <>
                        , воркеров: <b>{importMetrics.ocr_workers}</b>
                      </>
                    ) : null}
                  </span>
                ) : null}
                {importMetrics.parse_needs_review != null ? (
                  <span className="rounded-lg bg-rose-100/85 text-rose-950 px-2 py-1">
                    На проверку (needs_review): <b>{importMetrics.parse_needs_review}</b>
                  </span>
                ) : null}
                {importMetrics.parse_rows_total != null && importMetrics.stage === "geocode" ? (
                  <span className="rounded-lg bg-emerald-100/80 text-emerald-950 px-2 py-1 sm:col-span-2">
                    Разбор: строк <b>{importMetrics.parse_rows_total}</b>
                    {importMetrics.parse_low_confidence != null ? (
                      <>
                        , низк. уверенность: <b>{importMetrics.parse_low_confidence}</b>
                      </>
                    ) : null}
                    {importMetrics.parse_owner_empty != null ? (
                      <>
                        , без владельца: <b>{importMetrics.parse_owner_empty}</b>
                      </>
                    ) : null}
                    {importMetrics.parse_address_empty != null ? (
                      <>
                        , пустой адрес: <b>{importMetrics.parse_address_empty}</b>
                      </>
                    ) : null}
                    {importMetrics.parse_repair_pass_rows != null && importMetrics.parse_repair_pass_rows > 0 ? (
                      <>
                        , repair-pass: <b>{importMetrics.parse_repair_pass_rows}</b>
                      </>
                    ) : null}
                  </span>
                ) : null}
                {importMetrics.parsed_records != null ? (
                  <span className="rounded-lg bg-emerald-100/80 text-emerald-950 px-2 py-1">
                    Разобрано: <b>{importMetrics.parsed_records}</b>
                  </span>
                ) : null}
                {importMetrics.saved_records != null ? (
                  <span className="rounded-lg bg-emerald-100/80 text-emerald-950 px-2 py-1">
                    Сохранено: <b>{importMetrics.saved_records}</b>
                  </span>
                ) : null}
              </div>
            </div>
          ) : null}
          <p className="mt-2 text-xs text-emerald-900/50">
            {/\bстраница\s+\d+/i.test(importMessage) ? (
              <>
                Сейчас на сервере идёт извлечение текста из исходных файлов (это ещё не геокодирование). Для очень
                больших PDF этап может идти долго; если номер страницы долго не меняется — часто «тяжёлая» страница
                или режим pdfplumber. Убедитесь, что API собран с PyMuPDF по умолчанию и в{" "}
                <code className="rounded bg-emerald-100/80 px-1">
                  REGISTRY_PDF_TEXT_BACKEND
                </code>{" "}
                не задано{" "}
                <code className="rounded bg-emerald-100/80 px-1">
                  pdfplumber
                </code>
                .
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
    </>
  );
}
