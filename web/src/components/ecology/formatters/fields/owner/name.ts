const LEGAL_FORM_RE =
  /(?:^|[^A-Za-zА-Яа-яЁё0-9])((?:ООО|ОАО|ЗАО|УП|РУП|ЧУП|ОДО|ИП|КУП|ГУП|ГП|КПУП|КДУП|РУСП)(?=$|[^A-Za-zА-Яа-яЁё0-9])[\s\S]*)/i;
const ORG_HINT_RE =
  /(?:^|[^A-Za-zА-Яа-яЁё])(?:филиал|управлени[ея]|трест|комбинат|завод|предприят|организац|компан|дирекц|объединени|концерн|холдинг|служб)(?=$|[^A-Za-zА-Яа-яЁё])/i;

function normalizeOwnerTypos(text: string): string {
  return text
    .replace(/(^|[^A-Za-zА-Яа-яЁё])(филила)(?=$|[^A-Za-zА-Яа-яЁё])/gi, "$1филиал")
    .replace(/(^|[^A-Za-zА-Яа-яЁё])(филиол)(?=$|[^A-Za-zА-Яа-яЁё])/gi, "$1филиал")
    .replace(/(^|[^A-Za-zА-Яа-яЁё])(филл?иал)(?=$|[^A-Za-zА-Яа-яЁё])/gi, "$1филиал");
}

function trimOwnerNoiseTail(text: string): string {
  const cutMarkers = [
    /\b(?:Объект|Собственник)\b/i,
    /\b\d{6}\b/,
    /(?:\+?\s*375|8-0?\d{2,4}|\(\s*0\d{2,4}\s*\)|(?:^|[^A-Za-zА-Яа-яЁё])тел\.?(?=$|[^A-Za-zА-Яа-яЁё])|(?:^|[^A-Za-zА-Яа-яЁё])факс(?=$|[^A-Za-zА-Яа-яЁё]))/i,
    /\bв\s+соответствии\s+с\s+законодательством\b/i,
    /\bоб\s+охране\s+окружающей\s+среды\b/i,
    /\bиспользует\s+собственные\b/i,
    /\bпринимает\s+отходы?\s+от\s+других\b/i,
    /,\s*(?:г\.|ул\.|улица|д\.|аг\.|дер\.|пос\.)/i,
  ];
  const cuts = cutMarkers.map((re) => text.search(re)).filter((idx) => idx >= 0);
  const out = cuts.length > 0 ? text.slice(0, Math.min(...cuts)) : text;
  return out.trim();
}

function extractOwnerHintFromText(text: string, minScore = 45): string | null {
  const compact = normalizeOwnerTypos(text).replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
  if (!compact) return null;
  const segments = compact
    .split(/[;,]/)
    .map((s) => trimOwnerNoiseTail(s).replace(/^[*•"'«»\s\-–—]+/, "").replace(/[;,.:\-–—\s]+$/g, "").trim())
    .filter(Boolean);
  let best: { value: string; score: number } | null = null;
  for (const seg of segments) {
    if (/\b\d{6}\b/.test(seg)) continue;
    if (/(?:\+?\s*375|8-0?\d{2,4}|\(\s*0\d{2,4}\s*\)|(?:^|[^A-Za-zА-Яа-яЁё])тел\.?(?=$|[^A-Za-zА-Яа-яЁё])|(?:^|[^A-Za-zА-Яа-яЁё])факс(?=$|[^A-Za-zА-Яа-яЁё]))/i.test(seg)) continue;
    if (/\b(?:г\.|ул\.|улица|д\.|обл\.|область|район|р-н|аг\.|дер\.|пос\.)\b/i.test(seg)) continue;
    if (/\b(?:объект|собственник|использует|принимает)\b/i.test(seg)) continue;
    let score = 0;
    if (LEGAL_FORM_RE.test(seg)) score += 70;
    if (ORG_HINT_RE.test(seg)) score += 40;
    if (/[\"«»]/.test(seg)) score += 8;
    score += Math.min(20, Math.floor(seg.length / 7));
    if (isGenericOwnerFragment(seg)) score -= 60;
    if (!best || score > best.score || (score === best.score && seg.length > best.value.length)) {
      best = { value: seg, score };
    }
  }
  if (!best || best.score < minScore) return null;
  return best.value;
}

function extractLegalChunk(text: string): string | null {
  const compact = normalizeOwnerTypos(text).replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
  const m = compact.match(LEGAL_FORM_RE);
  if (!m) return null;
  const raw = (m[1] || "").trim();
  if (!raw) return null;
  const trimmed = trimOwnerNoiseTail(raw);
  return trimmed || null;
}

function withFilialPrefix(source: string, legalChunk: string): string {
  if (!source || !legalChunk) return legalChunk;
  if (/^филиал\b/i.test(legalChunk)) return legalChunk;
  const hasFilialBeforeLegal = /(?:^|[^A-Za-zА-Яа-яЁё])филиал\s+(?:ООО|ОАО|ЗАО|УП|РУП|ЧУП|ОДО|ИП)/i.test(source);
  return hasFilialBeforeLegal ? `филиал ${legalChunk}` : legalChunk;
}

function isGenericOwnerFragment(text: string): boolean {
  const t = text.trim().toLowerCase();
  return /^(?:управление|предприятие|организация|компания|филиал|участок|цех|отдел|дирекция|служба)$/.test(t);
}

export function formatOwnerDisplay(
  owner: string | null | undefined,
  objectName: string | null | undefined = "",
  address: string | null | undefined = "",
): string {
  const raw = normalizeOwnerTypos((owner || "").replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim());
  if (!raw) {
    const source = `${objectName || ""} ${address || ""}`;
    const guessedLegal = extractLegalChunk(source);
    if (guessedLegal) return withFilialPrefix(source, guessedLegal);
    const guessed = extractOwnerHintFromText(source, 40);
    return guessed || "—";
  }

  let cleaned = raw
    .replace(
      /\b\d{1,2}\s+[А-Яа-яA-Za-z]+(?:\s+\d{4})?\s*г\.\s*Страница\s*\d+\s*из\s*\d+\b.*$/gi,
      "",
    )
    .replace(/Использует[\s\S]*$/gi, "")
    .replace(/Принимает[\s\S]*?собственные[\s\S]*?от[\s\S]*?других/gi, "")
    .trim();

  const legalChunk = extractLegalChunk(cleaned);
  cleaned = trimOwnerNoiseTail(cleaned);
  if (legalChunk && (cleaned.length < 10 || legalChunk.length >= Math.max(14, Math.floor(cleaned.length * 0.65)))) {
    cleaned = withFilialPrefix(cleaned, legalChunk);
  }
  cleaned = cleaned.replace(/^[*•"'«»\s\-–—]+/, "").replace(/[;,.:\-–—\s]+$/g, "").trim();
  if (isGenericOwnerFragment(cleaned)) {
    const source = `${raw} ${objectName || ""} ${address || ""}`;
    const guessedLegal = extractLegalChunk(source);
    if (guessedLegal) return withFilialPrefix(source, guessedLegal);
    const guessed = extractOwnerHintFromText(source, 35);
    return guessed || "—";
  }

  return cleaned || extractOwnerHintFromText(`${raw} ${objectName || ""} ${address || ""}`, 35) || "—";
}
