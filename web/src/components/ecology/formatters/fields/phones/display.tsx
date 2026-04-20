import type { ReactNode } from "react";
import { formatPhoneSegmentToLines } from "../../../../../lib/phoneDisplay";

function dedupePhoneLines(lines: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const line of lines) {
    const key = line.replace(/\D/g, "");
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(line);
  }
  return out;
}

function isPhoneDisplayLineUseful(line: string): boolean {
  const s = (line || "").trim();
  if (!s) return false;
  const digits = s.replace(/\D/g, "");
  if (digits.length < 9 || digits.length > 12) return false;
  if (!s.includes("+375") && !s.includes("(") && !s.includes("-")) return false;
  return true;
}

export function formatPhonesDisplay(phones: string | null | undefined): ReactNode {
  const raw = phones?.trim() || "";
  if (!raw) return "Не указан в реестре";

  const parts = dedupePhoneLines(
    raw
      .split(/\s*;\s*/)
      .flatMap((p) => formatPhoneSegmentToLines(p.trim()))
      .filter(Boolean)
      .filter(isPhoneDisplayLineUseful),
  );

  if (parts.length === 0) return "Не указан в реестре";
  if (parts.length === 1) return parts[0];
  return (
    <>
      {parts.map((p, i) => (
        <span key={i} className="block">
          {p}
        </span>
      ))}
    </>
  );
}
