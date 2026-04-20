export function formatObjectCode(id: number | string | null | undefined): string {
  if (id == null) return "—";
  const text = String(id).trim();
  if (!text) return "—";
  const m = text.match(/\d{1,10}/);
  return m ? m[0] : "—";
}
