/**
 * Единый паттерн: таймаут через AbortController + опциональная отмена с родительского signal.
 */

export function isAbortError(e: unknown): boolean {
  return (
    (e instanceof DOMException && e.name === "AbortError") || (e instanceof Error && e.name === "AbortError")
  );
}

export type TimeoutLinkedAbort = {
  signal: AbortSignal;
  /** Снять таймер и listener родителя — вызывать в finally. */
  dispose: () => void;
  /** true если сработал внутренний таймаут (а не отмена родителя). */
  timedOut: () => boolean;
};

/**
 * Дочерний signal отменяется по таймауту или при abort родителя.
 */
export function createTimeoutLinkedAbort(
  timeoutMs: number,
  parentSignal: AbortSignal | undefined,
): TimeoutLinkedAbort {
  const ctrl = new AbortController();
  let timedOut = false;
  const id = setTimeout(() => {
    timedOut = true;
    ctrl.abort();
  }, timeoutMs);
  const onParentAbort = () => {
    ctrl.abort();
  };
  if (parentSignal) {
    if (parentSignal.aborted) ctrl.abort();
    else parentSignal.addEventListener("abort", onParentAbort, { once: true });
  }
  const dispose = () => {
    clearTimeout(id);
    parentSignal?.removeEventListener("abort", onParentAbort);
  };
  return {
    signal: ctrl.signal,
    dispose,
    timedOut: () => timedOut,
  };
}
