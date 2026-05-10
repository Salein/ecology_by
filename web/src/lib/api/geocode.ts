import { apiUrl, cred } from "./client";

export async function reverseGeocode(lat: number, lon: number): Promise<string | null> {
  const qs = new URLSearchParams({ lat: String(lat), lon: String(lon) }).toString();
  const r = await fetch(apiUrl(`/api/v1/geocode/reverse?${qs}`), { ...cred });
  if (!r.ok) throw new Error(`reverse geocode failed: ${r.status}`);
  const data = (await r.json()) as { display_name: string | null };
  const name = data.display_name?.trim();
  return name || null;
}
