"use client";

import { startTransition, useCallback, useEffect, useRef, useState } from "react";
import { reverseGeocode, searchObjects } from "@/lib/api";
import type { WasteObjectRow } from "@/lib/api";

function parseWasteSearchInput(input: string): { query: string; wasteCode: string | null } {
  const raw = input.trim();
  if (!raw) return { query: "", wasteCode: null };
  const byLabel = raw.match(/^(\d{7})\s*[—-]\s*(.+)$/);
  if (byLabel) {
    return { query: "", wasteCode: byLabel[1] };
  }
  const codeOnly = raw.match(/^(\d{7})$/);
  if (codeOnly) {
    return { query: "", wasteCode: codeOnly[1] };
  }
  return { query: raw, wasteCode: null };
}

export function useSearch(importBusy: boolean) {
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [lat, setLat] = useState<number | undefined>(undefined);
  const [lon, setLon] = useState<number | undefined>(undefined);
  const [addressLabel, setAddressLabel] = useState("");
  const [mapOpen, setMapOpen] = useState(false);
  const [rows, setRows] = useState<WasteObjectRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** Активный POST /objects/search — отменяем при импорте и при новом поиске. */
  const searchAbortRef = useRef<AbortController | null>(null);

  const abortSearch = useCallback(() => {
    searchAbortRef.current?.abort();
    searchAbortRef.current = null;
  }, []);

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
    const parsed = parseWasteSearchInput(query);
    const q = parsed.query;
    const wasteCode = parsed.wasteCode;
    if (!q && !wasteCode) {
      searchAbortRef.current?.abort();
      searchAbortRef.current = null;
      setRows([]);
      setError(null);
      setLoading(false);
      return;
    }
    const prev = searchAbortRef.current;
    if (prev) prev.abort();
    const ac = new AbortController();
    searchAbortRef.current = ac;
    setLoading(true);
    setError(null);
    try {
      const items = await searchObjects({
        query: q,
        wasteCode,
        lat,
        lon,
        signal: ac.signal,
      });
      if (searchAbortRef.current !== ac) return;
      startTransition(() => {
        setRows(items);
      });
    } catch (e) {
      if (searchAbortRef.current !== ac) return;
      const aborted =
        (e instanceof DOMException && e.name === "AbortError") ||
        (e instanceof Error && e.name === "AbortError");
      if (aborted) {
        setRows([]);
        return;
      }
      setError(e instanceof Error ? e.message : "Ошибка запроса");
      setRows([]);
    } finally {
      if (searchAbortRef.current === ac) {
        setLoading(false);
        searchAbortRef.current = null;
      }
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

  /** Применить строку запроса из подсказки (код — вид). */
  const commitQuery = useCallback((fullLabel: string) => {
    startTransition(() => {
      setQuery(fullLabel);
      setLoading(true);
      setError(null);
    });
  }, []);

  useEffect(() => {
    if (importBusy) return;
    if (lat == null || lon == null) return;
    const draft = queryInput.trim();
    if (draft === query) return;
    setLat(undefined);
    setLon(undefined);
    setAddressLabel("");
  }, [queryInput, query, lat, lon, importBusy]);

  useEffect(() => {
    void runSearch();
  }, [runSearch]);

  useEffect(() => {
    if (lat != null && lon != null) void refreshAddress(lat, lon);
    else setAddressLabel("");
  }, [lat, lon, refreshAddress]);

  const hasActiveQuery = query.trim().length > 0;
  const locationChosen = lat != null && lon != null;
  const showSearchLoader = loading && (hasActiveQuery || queryInput.trim().length > 0);
  const showSkeleton = hasActiveQuery && (importBusy || loading);
  const showDistanceSearchLoader = loading && locationChosen && !importBusy;

  return {
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
    runSearch,
    submitQuery,
    commitQuery,
    abortSearch,
    setLoading,
    hasActiveQuery,
    showSearchLoader,
    showSkeleton,
    showDistanceSearchLoader,
    locationChosen,
  };
}
