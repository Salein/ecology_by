"use client";

import { startTransition, useCallback, useEffect, useState } from "react";
import { fetchWasteSuggestions, isAbortError } from "@/lib/api";
import type { WasteSuggestItem } from "@/lib/api";

export function useWasteSuggest(options: {
  queryInput: string;
  setQueryInput: (v: string) => void;
  importBusy: boolean;
  commitQuery: (fullLabel: string) => void;
}) {
  const { queryInput, setQueryInput, importBusy, commitQuery } = options;
  const [wasteSuggest, setWasteSuggest] = useState<WasteSuggestItem[]>([]);
  const [showWasteSuggest, setShowWasteSuggest] = useState(false);
  const [wasteSuggestActive, setWasteSuggestActive] = useState(-1);

  const suggestionLabel = useCallback((it: WasteSuggestItem) => {
    return [it.waste_code, it.waste_type_name].filter(Boolean).join(" — ");
  }, []);

  const applySuggestion = useCallback(
    (it: WasteSuggestItem) => {
      const label = suggestionLabel(it);
      setQueryInput(label);
      setShowWasteSuggest(false);
      setWasteSuggestActive(-1);
      startTransition(() => {
        commitQuery(label);
      });
    },
    [suggestionLabel, setQueryInput, commitQuery],
  );

  const renderHighlightedLabel = useCallback((label: string, needleRaw: string) => {
    const needle = needleRaw.trim();
    if (!needle) return label;
    const lowLabel = label.toLowerCase();
    const lowNeedle = needle.toLowerCase();
    const idx = lowLabel.indexOf(lowNeedle);
    if (idx < 0) return label;
    return (
      <>
        {label.slice(0, idx)}
        <mark className="rounded bg-amber-100 px-0.5 text-emerald-950">{label.slice(idx, idx + needle.length)}</mark>
        {label.slice(idx + needle.length)}
      </>
    );
  }, []);

  useEffect(() => {
    if (importBusy) {
      setWasteSuggest([]);
      setShowWasteSuggest(false);
      return;
    }
    const q = queryInput.trim();
    if (q.length < 2) {
      setWasteSuggest([]);
      setShowWasteSuggest(false);
      return;
    }
    const ac = new AbortController();
    const timer = setTimeout(() => {
      void fetchWasteSuggestions(q, 12, ac.signal)
        .then((items) => {
          if (ac.signal.aborted) return;
          setWasteSuggest(items);
          setShowWasteSuggest(items.length > 0);
          setWasteSuggestActive(items.length > 0 ? 0 : -1);
        })
        .catch((e) => {
          if (ac.signal.aborted || isAbortError(e)) return;
          setWasteSuggest([]);
          setShowWasteSuggest(false);
          setWasteSuggestActive(-1);
        });
    }, 180);
    return () => {
      ac.abort();
      clearTimeout(timer);
    };
  }, [queryInput, importBusy]);

  return {
    wasteSuggest,
    showWasteSuggest,
    setShowWasteSuggest,
    wasteSuggestActive,
    setWasteSuggestActive,
    suggestionLabel,
    applySuggestion,
    renderHighlightedLabel,
  };
}
