function compactObjectText(value: string): string {
  const parts = value
    .split(",")
    .map((p) => p.trim())
    .filter(Boolean);
  if (parts.length <= 1) return value;

  const out: string[] = [];
  for (const part of parts) {
    const stopByAddress = /\b(?:г\.|ул\.|улица|д\.|дом|обл\.|область|район|р-н|с\/с|каб\.|оф\.)\b/i.test(part);
    const stopByService = /\b(?:Объект|Собственник|Использует|Принимает)\b/i.test(part);
    const stopByLegal = /(^|[^A-Za-zА-Яа-яЁё])(?:ООО|ОАО|ЗАО|УП|РУП|ЧУП|ОДО|ИП)(?=$|[^A-Za-zА-Яа-яЁё])/i.test(part);
    const stopByLegalLong =
      /(?:коммунальное|республиканское|государственное|частное)\s+унитарное\s+предприятие/i.test(part) ||
      /(?:коммунальное|государственное)\s+предприятие/i.test(part);
    const stopByPhone =
      /(?:\+?\s*375|8-0?\d{2,4}|\(\s*0\d{2,4}\s*\)|(?:^|[^A-Za-zА-Яа-яЁё])тел\.?(?=$|[^A-Za-zА-Яа-яЁё])|(?:^|[^A-Za-zА-Яа-яЁё])факс(?=$|[^A-Za-zА-Яа-яЁё]))/i.test(
        part,
      );
    if (stopByAddress || stopByService || stopByLegal || stopByLegalLong || stopByPhone) break;
    out.push(part);
    if (out.length >= 3) break;
  }

  return out.length > 0 ? out.join(", ") : parts[0];
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function formatObjectNameDisplay(
  objectName: string | null | undefined,
  wasteTypeName: string | null | undefined = "",
): string {
  let raw = (objectName || "").replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
  if (!raw) return "—";

  raw = raw
    .replace(
      /\b\d{1,2}\s+[А-Яа-яA-Za-z]+(?:\s+\d{4})?\s*г\.\s*Страница\s*\d+\s*из\s*\d+\b.*$/gi,
      "",
    )
    .trim();
  const cutMarkers = [
    /\b(?:Объект|Собственник)\b/i,
    /(^|[^A-Za-zА-Яа-яЁё])(?:ООО|ОАО|ЗАО|УП|РУП|ЧУП|ОДО|ИП)(?=$|[^A-Za-zА-Яа-яЁё])/i,
    /\b\d{6}\b/,
    /(?:\+?\s*375|8-0?\d{2,4}|\(\s*0\d{2,4}\s*\)|(?:^|[^A-Za-zА-Яа-яЁё])тел\.?(?=$|[^A-Za-zА-Яа-яЁё])|(?:^|[^A-Za-zА-Яа-яЁё])факс(?=$|[^A-Za-zА-Яа-яЁё]))/i,
    /\bв\s+соответствии\s+с\s+законодательством\b/i,
    /\bоб\s+охране\s+окружающей\s+среды\b/i,
  ];
  const cuts = cutMarkers.map((re) => raw.search(re)).filter((idx) => idx >= 0);
  let cleaned = cuts.length > 0 ? raw.slice(0, Math.min(...cuts)) : raw;
  cleaned = cleaned
    .replace(/объекты?\s*,?\s*которые\s+принимают\s+отходы?\s+от\s+других(?:\s+лиц)?/gi, " ")
    .replace(/принимает\s+от\s+других(?:\s+лиц)?/gi, " ")
    .replace(/принимает\s+отходы?\s+от\s+других(?:\s+лиц)?/gi, " ")
    .replace(/использует\s+собственные\s+отходы?/gi, " ")
    .replace(/^(?:от\s+других(?:\s+лиц)?[,:;\-–—\s]*)+/i, " ")
    .replace(/(?:коммунальное|республиканское|государственное|частное)\s+унитарное\s+предприятие.*$/i, "")
    .replace(/(?:коммунальное|государственное)\s+предприятие.*$/i, " ")
    .replace(/\s+/g, " ")
    .trim();
  const waste = (wasteTypeName || "").replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
  if (waste) {
    const wastePrefix = new RegExp(`^${escapeRegExp(waste)}(?:[\\s,;:.\\-–—]+)?`, "i");
    cleaned = cleaned.replace(wastePrefix, "").trim();
  }
  // Частый артефакт: поле "Объект" начинается с вида отхода (например "Бой ... Опытная установка ...").
  cleaned = cleaned.replace(
    /^(?:бой|отходы?|лом)\s+[^,;()]{3,140}?\s+(?=(?:опытн|мобильн|стационарн|дробильн|сортировочн|установк|комплекс|линия|цех|пункт|участок))/i,
    "",
  );
  cleaned = cleaned.replace(
    /^(?:(?:принимает(?:\s+отходы?)?\s+от\s+других(?:\s+лиц)?|использует\s+собственные\s+отходы?)\s+)?(?:бой|отходы?|лом)\s+[^,;()]{3,220}?\s+(?=(?:опытн|мобильн|стационарн|дробильн|сортировочн|установк|комплекс|линия|цех|пункт|участок))/i,
    "",
  );
  cleaned = compactObjectText(cleaned);
  cleaned = cleaned.replace(/^[*•"'«»\s\-–—]+/, "").replace(/[;,.:\-–—\s]+$/g, "").trim();
  if (/^(?:—|-|объект(?:ы)?)$/i.test(cleaned)) {
    return "Не указан в реестре";
  }
  if (cleaned.length > 220) {
    const short = cleaned.slice(0, 220);
    cleaned = (short.slice(0, short.lastIndexOf(" ")).trim() || short).trim() + "…";
  }
  cleaned = cleaned.replace(/(?:^|\s)(?:по|для|из|от|на|с|со|и)\s*$/i, "").trim();

  return cleaned || "Не указан в реестре";
}
