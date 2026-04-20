import type { ReactNode } from "react";

function cleanAddressNoise(address: string): string {
  let s = address
    .replace(/\u00a0/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\s+,/g, ",")
    .trim();

  const cutMarkers = [
    /\b(?:Объект|Собственник)\b/i,
    /(^|[^A-Za-zА-Яа-яЁё])(?:ООО|ОАО|ЗАО|УП|РУП|ЧУП|ОДО|ИП)(?=$|[^A-Za-zА-Яа-яЁё])/i,
    /\b(?:в\s+соответствии\s+с\s+законодательством|об\s+охране\s+окружающей\s+среды)\b/i,
  ];
  const cuts = cutMarkers.map((re) => s.search(re)).filter((idx) => idx >= 0);
  if (cuts.length > 0) s = s.slice(0, Math.min(...cuts)).trim();

  s = s
    .replace(/\b(?:тел\.?|факс)\s*[:.]?\s*[\d\s\-(),+]{5,}$/i, "")
    .replace(/(?:,\s*|\s+)\(?0\d{2,4}\)?[\d\s\-]{4,}$/i, "")
    .replace(/(?:,\s*|\s+)\+?375[\d\s\-()]{7,}$/i, "")
    .replace(/[,\s]+$/g, "")
    .trim();
  return s;
}

function compactAddress(address: string): string {
  const parts = address
    .split(",")
    .map((p) => p.trim())
    .filter(Boolean);
  if (parts.length === 0) return "";

  const dedup: string[] = [];
  const seen = new Set<string>();
  for (const part of parts) {
    const key = part.replace(/\s+/g, " ").trim().toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    dedup.push(part);
  }
  if (dedup.length === 0) return "";

  const cityIdx = dedup.findIndex((p) => /^г\.\s*[^\d,]+$/i.test(p));
  const streetIdx = dedup.findIndex((p) =>
    /^(?:ул\.|улица|просп\.|пр-т|пер\.|б-р|шоссе|наб\.|пл\.)\s*.+$/i.test(p),
  );
  if (cityIdx < 0 || streetIdx < 0 || streetIdx <= cityIdx) {
    return dedup.join(", ");
  }

  const city = dedup[cityIdx].replace(/\s+/g, " ").trim();
  let street = dedup[streetIdx].replace(/\s+/g, " ").trim();
  const next = dedup[streetIdx + 1] || "";
  if (next && /^\d+[A-Za-zА-Яа-я]?(?:\/\d+)?(?:-\d+)?$/.test(next.trim())) {
    street = `${street}, ${next.trim()}`;
  }
  return `${city}, ${street}`.replace(/[,\s]+$/g, "").trim();
}

export function formatAddressDisplay(address: string | null | undefined): ReactNode {
  const raw = (address || "").trim();
  if (!raw) return "—";

  const cleaned = compactAddress(cleanAddressNoise(raw));
  const m = cleaned.match(/^(\d{6})\s*,\s*(.+)$/);
  if (!m) return cleaned || "—";

  return m[2] || "—";
}
