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

/** Городская линия чаще 6 цифр: XX-XX-XX */
function groupLandlineLocal(d: string): string {
  if (d.length <= 4) return d;
  const parts: string[] = [];
  let i = 0;
  while (i < d.length) {
    const remaining = d.length - i;
    if (remaining <= 2) {
      parts.push(d.slice(i));
      break;
    }
    parts.push(d.slice(i, i + 2));
    i += 2;
  }
  return parts.join("-");
}

/** Мобильный абонентский 7 цифр: XXX-XX-XX */
function groupMobileLocal(d: string): string {
  if (d.length === 7) {
    return `${d.slice(0, 3)}-${d.slice(3, 5)}-${d.slice(5)}`;
  }
  return groupLandlineLocal(d);
}

/**
 * Два (или больше) номера без «;» в реестре: кратности 6 цифр подряд (12, 18…).
 */
function splitGluedLocalDigits(d: string): string[] {
  const n = d.length;
  if (n >= 12 && n % 6 === 0) {
    const parts: string[] = [];
    for (let i = 0; i < n; i += 6) {
      parts.push(d.slice(i, i + 6));
    }
    return parts;
  }
  return [d];
}

function formatByAreaAndLocal(area: string, localDigits: string): string {
  const loc =
    BY_MOBILE_OPERATORS.has(area) && localDigits.length === 7
      ? groupMobileLocal(localDigits)
      : groupLandlineLocal(localDigits);
  return `+375 (${area}) ${loc}`;
}

/** Нормализация уже введённого +375 … */
function normalizeExisting375(s: string): string {
  let t = s.replace(/\u00a0/g, " ").trim();
  t = t.replace(/^\+?\s*375\s*/i, "+375 ");
  t = t.replace(/\s+/g, " ").trim();
  return t;
}

/**
 * Одна строка до «;» → одна или несколько строк для отображения (склейка 6+6 даёт две).
 */
export function formatPhoneSegmentToLines(raw: string): string[] {
  const s = sanitizePhoneSegment(raw);
  if (!s) return [];

  const compact = s.replace(/\s/g, "");
  if (/^\+?375/.test(compact)) {
    return [normalizeExisting375(s)];
  }

  const m = s.match(/^\(([^)]+)\)\s*(.*)$/);
  if (!m) {
    return [s];
  }

  const codeDigits = m[1].replace(/\D/g, "");
  const localDigits = m[2].replace(/\D/g, "");
  if (!codeDigits) {
    return [`(${m[1].trim()})${localDigits ? ` ${localDigits}` : ""}`];
  }

  let area = codeDigits.startsWith("0") ? codeDigits.slice(1) : codeDigits;
  if (!area) {
    return [`(${m[1].trim()})`];
  }

  if (!localDigits) {
    return [`+375 (${area})`];
  }

  const locals = splitGluedLocalDigits(localDigits);
  return locals.map((loc) => formatByAreaAndLocal(area, loc));
}

/** Одна строка в одну линию (для простых случаев). */
export function formatPhoneForDisplay(raw: string): string {
  return formatPhoneSegmentToLines(raw).join("; ");
}

export function formatPhonePartsForDisplay(parts: string[]): string[] {
  return parts.flatMap((p) => formatPhoneSegmentToLines(p));
}
