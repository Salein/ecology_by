"use client";

import { useCallback, useEffect, useState } from "react";
import { MapContainer, Marker, TileLayer, useMapEvents } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

const MINSK: [number, number] = [53.9045, 27.5615];

function defaults() {
  delete (L.Icon.Default.prototype as unknown as { _getIconUrl?: unknown })._getIconUrl;
  L.Icon.Default.mergeOptions({
    iconRetinaUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png",
    iconUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png",
    shadowUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png",
  });
}

function ClickHandler({
  onPick,
}: {
  onPick: (lat: number, lon: number) => void;
}) {
  useMapEvents({
    click(e) {
      onPick(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

type OpenProps = {
  onClose: () => void;
  initialLat?: number;
  initialLon?: number;
  onConfirm: (lat: number, lon: number) => void;
};

function LocationMapModalOpen({
  onClose,
  initialLat,
  initialLon,
  onConfirm,
}: OpenProps) {
  const [pos, setPos] = useState<[number, number]>(() => [
    initialLat ?? MINSK[0],
    initialLon ?? MINSK[1],
  ]);

  const onPick = useCallback((lat: number, lon: number) => {
    setPos([lat, lon]);
  }, []);

  useEffect(() => {
    defaults();
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-label="Выбор местоположения на карте"
    >
      <div className="flex max-h-[88vh] w-full max-w-[min(100%,64rem)] flex-col overflow-hidden rounded-2xl border border-emerald-100/80 bg-white shadow-xl shadow-emerald-900/5">
        <div className="flex shrink-0 items-center justify-between border-b border-emerald-100 bg-emerald-50/50 px-4 py-3">
          <h2 className="text-lg font-medium text-emerald-950">Карта OpenStreetMap</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full px-3 py-1 text-sm text-emerald-900/70 hover:bg-emerald-100/80"
          >
            Закрыть
          </button>
        </div>
        <p className="shrink-0 px-4 py-2 text-sm text-emerald-900/65">
          Нажмите на карту, чтобы поставить метку. Тайлы: © участники OpenStreetMap.
        </p>
        <div className="relative min-h-[200px] w-full shrink-0 overflow-hidden">
          <MapContainer
            center={pos}
            zoom={12}
            className="z-0 h-[min(42vh,320px)] w-full sm:h-[min(46vh,380px)] md:h-[min(48vh,420px)]"
            scrollWheelZoom
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            <ClickHandler onPick={onPick} />
            <Marker position={pos} />
          </MapContainer>
        </div>
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2 border-t border-emerald-100 bg-emerald-50/30 px-4 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-emerald-200/90 bg-white px-4 py-2 text-sm font-medium text-emerald-900/80 hover:bg-emerald-50"
          >
            Отмена
          </button>
          <button
            type="button"
            onClick={() => onConfirm(pos[0], pos[1])}
            className="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-medium text-white shadow-sm shadow-emerald-900/15 transition hover:bg-emerald-700"
          >
            Подтвердить
          </button>
        </div>
      </div>
    </div>
  );
}

type Props = {
  open: boolean;
  onClose: () => void;
  initialLat?: number;
  initialLon?: number;
  onConfirm: (lat: number, lon: number) => void;
};

export function LocationMapModal({ open, onClose, initialLat, initialLon, onConfirm }: Props) {
  if (!open) return null;
  return (
    <LocationMapModalOpen
      onClose={onClose}
      initialLat={initialLat}
      initialLon={initialLon}
      onConfirm={onConfirm}
    />
  );
}
