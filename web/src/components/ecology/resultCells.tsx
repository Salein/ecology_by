import type { WasteObjectRow } from "@/lib/api";
import {
  distanceIsMissing,
  formatAddressDisplay,
  formatDistance,
  formatObjectCode,
  formatObjectNameDisplay,
  formatOwnerDisplay,
  formatPhonesDisplay,
  formatSpread,
} from "./formatters";

type DistanceCellProps = {
  row: WasteObjectRow;
  locationChosen: boolean;
  distanceNotCalculatedNote: string;
  roadDistanceNotCalculatedNote: string;
};

export function CodeCell({ row }: { row: WasteObjectRow }) {
  return (
    <div className="text-xs font-semibold text-emerald-900/90 sm:pt-0.5 sm:text-sm">
      {formatObjectCode(row.id)}
    </div>
  );
}

export function OwnerCell({ row }: { row: WasteObjectRow }) {
  return (
    <div className="min-w-0 break-words text-sm leading-snug text-stone-800 sm:pt-0.5">
      {formatOwnerDisplay(row.owner, row.object_name, row.address)}
    </div>
  );
}

export function ObjectCell({ row }: { row: WasteObjectRow }) {
  const fullObjectName = formatObjectNameDisplay(row.object_name, row.waste_type_name);
  const isLong = fullObjectName.length > 90;
  return (
    <div className="flex min-w-0 flex-col gap-2 rounded-xl border border-emerald-100/70 bg-emerald-50/70 px-4 py-3 text-sm leading-snug text-stone-800 break-words">
      <span
        className="min-w-0"
        title={fullObjectName}
        style={
          isLong
            ? {
                display: "-webkit-box",
                WebkitLineClamp: 4,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
              }
            : undefined
        }
      >
        {fullObjectName}
      </span>
    </div>
  );
}

export function AddressCell({ row }: { row: WasteObjectRow }) {
  return (
    <div className="min-w-0">
      <span className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-emerald-800/40 sm:sr-only">
        Адрес объекта
      </span>
      <div className="min-w-0 break-words rounded-xl border border-emerald-100/70 bg-emerald-50/40 px-4 py-3 text-sm leading-relaxed text-stone-800">
        {formatAddressDisplay(row.address)}
      </div>
    </div>
  );
}

export function PhonesCell({ row }: { row: WasteObjectRow }) {
  return (
    <div className="min-w-0">
      <span className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-emerald-800/40 sm:sr-only">
        Телефоны
      </span>
      <div className="rounded-xl border border-emerald-100/70 bg-emerald-50/40 px-4 py-3 text-xs leading-relaxed text-stone-800 break-words tabular-nums">
        {formatPhonesDisplay(row.phones)}
      </div>
    </div>
  );
}

export function AirDistanceCell({
  row,
  locationChosen,
  distanceNotCalculatedNote,
}: Omit<DistanceCellProps, "roadDistanceNotCalculatedNote">) {
  return (
    <div className="flex min-w-0 w-full flex-col items-stretch gap-1.5 sm:items-end sm:justify-end sm:pt-0.5">
      <span
        className="inline-flex w-full justify-center rounded-xl border border-emerald-200/60 bg-emerald-100/95 px-3 py-2.5 text-xs font-medium text-emerald-900"
        title={locationChosen && distanceIsMissing(row.distance_air_km) ? distanceNotCalculatedNote : undefined}
      >
        {formatDistance(row.distance_air_km)}
      </span>
      {row.distance_is_approx && row.distance_spread_km != null ? (
        <span
          className="w-full text-right text-[11px] leading-snug text-emerald-900/85 sm:max-w-[14.5rem]"
          title={row.distance_spread_note || "Ориентировочный разброс"}
        >
          {`примерно ${formatSpread(row.distance_spread_km)}`}
        </span>
      ) : null}
      {locationChosen && distanceIsMissing(row.distance_air_km) ? (
        <span className="w-full text-right text-[11px] leading-snug text-amber-900/70 sm:max-w-[14.5rem]">
          {distanceNotCalculatedNote}
        </span>
      ) : null}
    </div>
  );
}

export function RoadDistanceCell({
  row,
  locationChosen,
  roadDistanceNotCalculatedNote,
}: Pick<DistanceCellProps, "row" | "locationChosen" | "roadDistanceNotCalculatedNote">) {
  return (
    <div className="flex min-w-0 w-full flex-col items-stretch gap-1.5 sm:items-end sm:justify-end sm:pt-0.5">
      <span
        className="inline-flex w-full justify-center rounded-xl border border-emerald-200/60 bg-emerald-100/95 px-3 py-2.5 text-xs font-medium text-emerald-900"
        title={
          locationChosen && distanceIsMissing(row.distance_road_km)
            ? row.distance_road_error?.trim() || roadDistanceNotCalculatedNote
            : undefined
        }
      >
        {formatDistance(row.distance_road_km)}
      </span>
      {locationChosen && distanceIsMissing(row.distance_road_km) ? (
        <span className="w-full text-right text-[11px] leading-snug text-amber-900/80 sm:max-w-[14.5rem]">
          {row.distance_road_error?.trim() || roadDistanceNotCalculatedNote}
        </span>
      ) : row.distance_is_approx && row.distance_spread_km != null ? (
        <span
          className="w-full text-right text-[11px] leading-snug text-emerald-900/85 sm:max-w-[14.5rem]"
          title={row.distance_spread_note || "Ориентировочный разброс"}
        >
          {`примерно ${formatSpread(row.distance_spread_km)}`}
        </span>
      ) : null}
    </div>
  );
}
