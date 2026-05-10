"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  chunkFilesForRegistryImport,
  fetchRegistryCacheMetaResult,
  fetchRegistryImportStatus,
  postRegistryImportWithUploadProgress,
  registryImportBatchProgress,
} from "@/lib/api";
import type { RegistryCacheMeta, RegistryImportStatus } from "@/lib/api";
import { yieldToPaint } from "../explorerUtils";

export function useRegistryImport(options: {
  importBusy: boolean;
  setImportBusy: (v: boolean) => void;
  abortSearch: () => void;
  runSearch: () => Promise<void>;
  setLoading: (v: boolean) => void;
  onCacheMetaUpdate: (
    meta: RegistryCacheMeta | null,
    ready: boolean,
    err: string | null,
    serverImportInProgress?: boolean,
  ) => void;
}) {
  const { importBusy, setImportBusy, abortSearch, runSearch, setLoading, onCacheMetaUpdate } = options;
  const fileRef = useRef<HTMLInputElement>(null);
  const [importProgress, setImportProgress] = useState(0);
  const [importMessage, setImportMessage] = useState("");
  const [importError, setImportError] = useState<string | null>(null);
  const [importMetrics, setImportMetrics] = useState<RegistryImportStatus["metrics"] | null>(null);
  const [uploadEtaSec, setUploadEtaSec] = useState<number | null>(null);
  const [uploadSpeedMbps, setUploadSpeedMbps] = useState<number | null>(null);
  const [uploadPhase, setUploadPhase] = useState<"uploading" | "waiting_server">("uploading");
  const [importElapsedSec, setImportElapsedSec] = useState(0);
  const importStartedAtRef = useRef<number | null>(null);

  useEffect(() => {
    if (!importBusy) return;
    if (importStartedAtRef.current == null) importStartedAtRef.current = Date.now();
    const t = setInterval(() => {
      if (importStartedAtRef.current == null) return;
      setImportElapsedSec(Math.max(0, Math.round((Date.now() - importStartedAtRef.current) / 1000)));
    }, 1000);
    return () => clearInterval(t);
  }, [importBusy]);

  const totalEtaSec = useMemo(() => {
    let total = 0;
    let hasAny = false;
    if (uploadEtaSec != null && importProgress <= 40) {
      total += Math.max(0, uploadEtaSec);
      hasAny = true;
    }
    if (importMetrics?.stage_eta_sec != null) {
      total += Math.max(0, importMetrics.stage_eta_sec);
      hasAny = true;
    }
    if (importMetrics?.queue_eta_sec != null && importMetrics.queue_eta_sec > 0) {
      total += Math.max(0, importMetrics.queue_eta_sec);
      hasAny = true;
    } else if (importMetrics?.queue_position != null && importMetrics.queue_position > 0) {
      const avgJobSec = Math.max(30, importMetrics?.avg_job_sec ?? 180);
      total += importMetrics.queue_position * avgJobSec;
      hasAny = true;
    }
    return hasAny ? total : null;
  }, [
    uploadEtaSec,
    importProgress,
    importMetrics?.stage_eta_sec,
    importMetrics?.queue_eta_sec,
    importMetrics?.queue_position,
    importMetrics?.avg_job_sec,
  ]);

  const importTimeline = useMemo(() => {
    const stage = (importMetrics?.stage || "").trim();
    const done = new Set<string>();
    if (!importMetrics) return { done, current: "" };
    if (stage === "queued") {
      return { done, current: "queued" };
    }
    if (stage === "ocr") {
      done.add("queued");
      return { done, current: "ocr" };
    }
    if (stage === "extract") {
      done.add("queued");
      done.add("ocr");
      return { done, current: "extract" };
    }
    if (stage === "checkbox") {
      done.add("queued");
      done.add("ocr");
      done.add("extract");
      return { done, current: "checkbox" };
    }
    if (stage === "geocode") {
      done.add("queued");
      done.add("ocr");
      done.add("extract");
      done.add("checkbox");
      return { done, current: "geocode" };
    }
    return { done, current: stage };
  }, [importMetrics]);

  const handleRegistryFiles = useCallback(
    async (list: FileList | null) => {
      if (!list?.length) return;
      const files = Array.from(list).filter((f) =>
        /\.(pdf|jpe?g|png|webp|bmp|tiff?|html?|txt)$/i.test(f.name),
      );
      if (!files.length) {
        setImportError("Выберите PDF/JPEG/PNG/WEBP/HTML/TXT.");
        return;
      }
      setImportError(null);
      abortSearch();
      setLoading(false);
      setImportBusy(true);
      setImportProgress(0);
      setImportMessage("Подготовка загрузки…");
      setUploadEtaSec(null);
      setUploadSpeedMbps(null);
      setUploadPhase("uploading");
      setImportElapsedSec(0);
      importStartedAtRef.current = Date.now();
      try {
        const total = files.length;
        const batches = chunkFilesForRegistryImport(files);
        const batchTotal = batches.length;
        setImportMetrics(null);

        const metaSnap = await fetchRegistryCacheMetaResult();
        const appendEntireSession =
          metaSnap.ok &&
          metaSnap.cache != null &&
          (metaSnap.cache.record_count ?? 0) > 0;

        if (appendEntireSession) {
          setImportMessage(
            "В кэше уже есть записи — импорт дополнит их (без полной замены кэша первой партией).",
          );
          await yieldToPaint();
        }

        for (let bi = 0; bi < batchTotal; bi++) {
          const batch = batches[bi]!;
          setImportMessage(
            batchTotal > 1
              ? `Партия ${bi + 1} из ${batchTotal}: отправка файлов (${batch.length} из ${total})…`
              : `Отправка пакета файлов (${total}) на сервер…`,
          );

          // Первая партия с replace при пустом кэше — ок (одна сессия из N пачек). Если в БД уже
          // есть записи, replace на первой пачке обнулил бы остальной реестр — только append.
          const mode: "replace" | "append" = appendEntireSession || bi > 0 ? "append" : "replace";
          const post = await postRegistryImportWithUploadProgress(batch, (up) => {
            setUploadPhase(up.phase);
            setImportProgress(registryImportBatchProgress(bi, batchTotal, "upload", up.pct, 0));
            setUploadEtaSec(up.etaSec);
            setUploadSpeedMbps(up.speedMbps);
            if (up.phase === "waiting_server") {
              setImportMessage(
                batchTotal > 1
                  ? `Партия ${bi + 1} из ${batchTotal}: файлы переданы, сервер принимает (${batch.length} файлов)…`
                  : `Файлы переданы. Сервер принимает пакет и ставит задачу в очередь (${total})…`,
              );
            } else {
              setImportMessage(
                batchTotal > 1
                  ? `Партия ${bi + 1} из ${batchTotal}: отправка (${batch.length} из ${total})…`
                  : `Отправка пакета файлов (${total}) на сервер…`,
              );
            }
          }, mode);

          if (post.skipped) {
            if (post.cache) {
              const snap = await fetchRegistryCacheMetaResult();
              if (snap.ok) {
                onCacheMetaUpdate(post.cache, true, null, snap.registry_import_in_progress);
              } else {
                onCacheMetaUpdate(post.cache, true, null);
              }
            } else {
              const res = await fetchRegistryCacheMetaResult();
              if (res.ok) {
                onCacheMetaUpdate(res.cache, true, null, res.registry_import_in_progress);
              } else {
                onCacheMetaUpdate(null, true, res.reason);
              }
            }
            setImportMessage(
              batchTotal > 1
                ? `Партия ${bi + 1} из ${batchTotal}: ${post.message || "Данные совпадают с кэшем — пропуск."}`
                : post.message || "Данные совпадают с кэшем — импорт пропущен.",
            );
            setImportProgress(registryImportBatchProgress(bi, batchTotal, "poll", 100, 100));
            continue;
          }

          let transientStatusFails = 0;
          for (;;) {
            let st: RegistryImportStatus;
            try {
              st = await fetchRegistryImportStatus(post.job_id);
              transientStatusFails = 0;
            } catch (statusErr) {
              const msg =
                statusErr instanceof Error && statusErr.message
                  ? statusErr.message
                  : String(statusErr || "");
              const transient =
                /(?:\b502\b|\b503\b|\b504\b|timeout|timed out|fetch|network|сеть|import status: timed out)/i.test(
                  msg,
                );
              if (transient && transientStatusFails < 25) {
                transientStatusFails += 1;
                setImportMessage(
                  batchTotal > 1
                    ? `Партия ${bi + 1} из ${batchTotal}: связь с API прервалась, ждём…`
                    : "Связь с API прервалась, ждём восстановление…",
                );
                await new Promise((r) => setTimeout(r, 700));
                continue;
              }
              throw statusErr;
            }

            setImportMessage(
              batchTotal > 1
                ? `Партия ${bi + 1} из ${batchTotal}: ${st.message || st.status}`
                : st.message || st.status,
            );
            setImportMetrics(st.metrics ?? null);
            setImportProgress(registryImportBatchProgress(bi, batchTotal, "poll", 100, st.progress));
            setUploadEtaSec(null);
            setUploadSpeedMbps(null);
            setUploadPhase("uploading");
            await yieldToPaint();
            if (st.status === "done") break;
            if (st.status === "error") {
              const detail = (st.message && st.message.trim()) || st.error || "Ошибка обработки реестра";
              throw new Error(detail);
            }
            await new Promise((r) => setTimeout(r, 450));
          }
        }

        const res = await fetchRegistryCacheMetaResult();
        if (res.ok) {
          onCacheMetaUpdate(res.cache, true, null, res.registry_import_in_progress);
        } else {
          onCacheMetaUpdate(null, true, res.reason);
        }
        setImportMessage("Готово. Обновляем список…");
        setImportProgress(100);
        setImportMetrics(null);
        setImportBusy(false);
        await runSearch();
      } catch (e) {
        const msg = e instanceof Error && e.message ? e.message : "Ошибка загрузки";
        setImportError(msg);
      } finally {
        setImportBusy(false);
        setImportProgress(0);
        setImportMessage("");
        setImportMetrics(null);
        setUploadEtaSec(null);
        setUploadSpeedMbps(null);
        setUploadPhase("uploading");
        setImportElapsedSec(0);
        importStartedAtRef.current = null;
        if (fileRef.current) fileRef.current.value = "";
      }
    },
    [abortSearch, runSearch, setLoading, onCacheMetaUpdate],
  );

  return {
    fileRef,
    importBusy,
    importProgress,
    importMessage,
    importError,
    setImportError,
    importMetrics,
    uploadEtaSec,
    uploadSpeedMbps,
    uploadPhase,
    importElapsedSec,
    totalEtaSec,
    importTimeline,
    handleRegistryFiles,
  };
}
