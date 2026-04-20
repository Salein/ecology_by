const EM_DASH = "—";

export function formatDistance(km: number | null | undefined): string {
  if (km == null || Number.isNaN(km)) return EM_DASH;
  return `~${Math.round(km)} км`;
}

export function formatSpread(km: number | null | undefined): string {
  if (km == null || Number.isNaN(km)) return "";
  return `±${Math.round(km)} км`;
}

export function distanceIsMissing(km: number | null | undefined): boolean {
  return km == null || Number.isNaN(Number(km));
}
