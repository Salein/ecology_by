/** Даём браузеру отрисовать кадр после обновления стейта (импорт/поллинг). */
export function yieldToPaint(): Promise<void> {
  return new Promise((resolve) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => resolve());
    });
  });
}

export const EM_DASH = "—";

export function formatEta(sec: number | null | undefined): string {
  if (sec == null || !Number.isFinite(sec) || sec < 0) return EM_DASH;
  const s = Math.max(0, Math.round(sec));
  const mm = Math.floor(s / 60);
  const ss = s % 60;
  if (mm <= 0) return `${ss} c`;
  return `${mm}м ${ss.toString().padStart(2, "0")}с`;
}

export function formatImportStage(stage: string | null | undefined): string {
  switch ((stage || "").trim()) {
    case "queued":
      return "В очереди";
    case "ocr":
      return "OCR изображений";
    case "extract":
      return "Извлечение текста";
    case "llm_batch":
      return "LLM-обработка батчей";
    case "llm_repair":
      return "LLM-починка полей";
    case "llm_post_checkbox":
      return "LLM после чекбоксов PDF";
    case "db_save_batch":
      return "Сохранение батча в БД";
    case "checkbox":
      return "Чекбоксы в PDF";
    case "geocode":
      return "Геокодирование";
    default:
      return stage?.trim() || EM_DASH;
  }
}
