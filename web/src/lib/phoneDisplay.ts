/**
 * Телефоны из реестра РБ: национальный вид «(0XX) …» → международный +375 (XX) …,
 * склеенные два городских номера (6+6 цифр) разделяются, мобильные 29/33/44/25 — по 7 цифр.
 */

const BY_MOBILE_OPERATORS = new Set(["25", "29", "33", "44"]);

function sanitizePhoneSegment(s: string): string {
  let t = s.replace(/\u00a0/g, " ").trim().replace(/\s+/g, " ");
  t = t.replace(/[\s.\-–—]+$/g, "");
  return t.trim();
}

/** РБ: длина местного номера = 9 - длина кода (без ведущего 0). */
function getExpectedLandlineLocalLength(area: string): number | null {
  if (BY_MOBILE_OPERATORS.has(area)) return 7;
  if (!/^\d+$/.test(area)) return null;
  const len = 9 - area.length;
  return len >= 5 && len <= 7 ? len : null;
}

/** Группировка городского местного номера в РБ по типичным шаблонам. */
function groupLandlineLocal(d: string, expectedLen?: number | null): string {
  if (d.length <= 4) return d;
  if (expectedLen === 7 && d.length === 7) {
    return `${d.slice(0, 3)}-${d.slice(3, 5)}-${d.slice(5)}`;
  }
  if (expectedLen === 6 && d.length === 6) {
    return `${d.slice(0, 2)}-${d.slice(2, 4)}-${d.slice(4)}`;
  }
  if (expectedLen === 5 && d.length === 5) {
    return `${d.slice(0, 2)}-${d.slice(2)}`;
  }
  const parts = d.match(/\d{1,2}/g);
  return parts ? parts.join("-") : d;
}

/** Мобильный абонентский 7 цифр: XXX-XX-XX */
function groupMobileLocal(d: string): string {
  if (d.length === 7) {
    return `${d.slice(0, 3)}-${d.slice(3, 5)}-${d.slice(5)}`;
  }
  return groupLandlineLocal(d, 7);
}

/**
 * Два (или больше) номера без «;» в реестре: делим по ожидаемой длине местного номера.
 */
function splitGluedLocalDigits(d: string, localLen: number | null): string[] {
  const n = d.length;
  if (localLen != null && localLen >= 5 && n >= localLen * 2 && n % localLen === 0) {
    const parts: string[] = [];
    for (let i = 0; i < n; i += localLen) {
      parts.push(d.slice(i, i + localLen));
    }
    return parts;
  }
  // В реестре встречаются «склейки» городских 6-значных локальных номеров
  // даже там, где по коду обычно ожидается 7 цифр (например, с потерянным префиксом).
  if (n >= 12 && n % 6 === 0) {
    const parts: string[] = [];
    for (let i = 0; i < n; i += 6) {
      parts.push(d.slice(i, i + 6));
    }
    return parts;
  }
  return [d];
}

function formatByAreaAndLocal(area: string, localDigits: string): string | null {
  const expectedLandlineLen = getExpectedLandlineLocalLength(area);
  if (expectedLandlineLen != null && localDigits.length < expectedLandlineLen) {
    return null;
  }
  if (expectedLandlineLen != null && localDigits.length !== expectedLandlineLen) {
    return `+375 (${area}) ${localDigits}`;
  }
  const loc =
    BY_MOBILE_OPERATORS.has(area) && localDigits.length === 7
      ? groupMobileLocal(localDigits)
      : groupLandlineLocal(localDigits, expectedLandlineLen);
  return `+375 (${area}) ${loc}`;
}

/** Нормализация уже введённого +375 … */
function normalizeExisting375(s: string): string {
  let t = s.replace(/\u00a0/g, " ").trim();
  t = t.replace(/^\+?\s*375\s*/i, "+375 ");
  t = t.replace(/\s+/g, " ").trim();
  return t;
}

function splitByFullNationalNumbers(significant: string): string[] | null {
  if (significant.length >= 9 && significant.length % 9 === 0) {
    const out: string[] = [];
    for (let i = 0; i < significant.length; i += 9) {
      out.push(significant.slice(i, i + 9));
    }
    return out;
  }
  return null;
}

function isClearlyIncompleteBelarusNumber(raw: string): boolean {
  const d = raw.replace(/\D/g, "");
  if (!d) return false;
  // Полный международный формат РБ: 375 + 9 значащих цифр.
  if (d.startsWith("375")) return d.length < 12;
  // Междугородний префикс 80 + 9 значащих цифр.
  if (d.startsWith("80")) return d.length < 11;
  // Национальный формат 0 + 9 значащих цифр.
  if (d.startsWith("0")) return d.length < 10;
  return false;
}

function parseAreaAndLocals(significant: string): { area: string; locals: string[] } | null {
  if (!/^\d+$/.test(significant) || significant.length < 7) return null;

  const mobileArea = significant.slice(0, 2);
  if (BY_MOBILE_OPERATORS.has(mobileArea) && significant.length >= 9) {
    const localLen = 7;
    const localDigits = significant.slice(2);
    if (localDigits.length % localLen === 0) {
      const locals: string[] = [];
      for (let i = 0; i < localDigits.length; i += localLen) {
        locals.push(localDigits.slice(i, i + localLen));
      }
      return { area: mobileArea, locals };
    }
    if (localDigits.length === localLen) {
      return { area: mobileArea, locals: [localDigits] };
    }
  }

  for (let areaLen = 4; areaLen >= 2; areaLen -= 1) {
    if (significant.length <= areaLen) continue;
    const area = significant.slice(0, areaLen);
    const localLen = getExpectedLandlineLocalLength(area);
    if (localLen == null) continue;
    const localDigits = significant.slice(areaLen);
    if (localDigits.length < localLen) continue;
    if (localDigits.length % localLen !== 0) continue;
    const locals: string[] = [];
    for (let i = 0; i < localDigits.length; i += localLen) {
      locals.push(localDigits.slice(i, i + localLen));
    }
    return { area, locals };
  }

  return null;
}

function formatCompactBelarusNumber(raw: string): string[] | null {
  const d = raw.replace(/\D/g, "");
  if (!d) return null;

  let significant = d;
  if (d.startsWith("375")) {
    significant = d.slice(3);
  } else if (d.startsWith("80")) {
    significant = d.slice(2);
  } else if (d.startsWith("0")) {
    significant = d.slice(1);
  }
  if (!significant) return null;

  const fullChunks = splitByFullNationalNumbers(significant);
  if (fullChunks) {
    const lines: string[] = [];
    for (const chunk of fullChunks) {
      const parsed = parseAreaAndLocals(chunk);
      if (!parsed || parsed.locals.length === 0) {
        lines.push(raw);
        continue;
      }
      lines.push(formatByAreaAndLocal(parsed.area, parsed.locals[0]));
    }
    return lines;
  }

  const parsed = parseAreaAndLocals(significant);
  if (!parsed || parsed.locals.length === 0) return null;
  return parsed.locals.map((loc) => formatByAreaAndLocal(parsed.area, loc)).filter((x): x is string => Boolean(x));
}

/**
 * Одна строка до «;» → одна или несколько строк для отображения (склейка 6+6 даёт две).
 */
export function formatPhoneSegmentToLines(raw: string): string[] {
  const s = sanitizePhoneSegment(raw);
  if (!s) return [];

  const compact = s.replace(/\s/g, "");
  if (/^\+?375/.test(compact)) {
    const compactParsed = formatCompactBelarusNumber(s);
    if (compactParsed && compactParsed.length > 0) return compactParsed;
    if (isClearlyIncompleteBelarusNumber(s)) return [];
    return [normalizeExisting375(s)];
  }

  const m = s.match(/^\(([^)]+)\)\s*(.*)$/);
  if (!m) {
    const compactParsed = formatCompactBelarusNumber(s);
    if (compactParsed && compactParsed.length > 0) return compactParsed;
    if (isClearlyIncompleteBelarusNumber(s)) return [];
    return [s];
  }

  const codeDigits = m[1].replace(/\D/g, "");
  const localDigits = m[2].replace(/\D/g, "");
  if (!codeDigits) {
    return [`(${m[1].trim()})${localDigits ? ` ${localDigits}` : ""}`];
  }

  const area = codeDigits.startsWith("0") ? codeDigits.slice(1) : codeDigits;
  if (!area) {
    return [`(${m[1].trim()})`];
  }

  if (!localDigits) {
    return [`+375 (${area})`];
  }

  const expectedLen = getExpectedLandlineLocalLength(area);
  const locals = splitGluedLocalDigits(localDigits, expectedLen);
  return locals.map((loc) => formatByAreaAndLocal(area, loc)).filter((x): x is string => Boolean(x));
}

/** Одна строка в одну линию (для простых случаев). */
export function formatPhoneForDisplay(raw: string): string {
  return formatPhoneSegmentToLines(raw).join("; ");
}

export function formatPhonePartsForDisplay(parts: string[]): string[] {
  return parts.flatMap((p) => formatPhoneSegmentToLines(p));
}
