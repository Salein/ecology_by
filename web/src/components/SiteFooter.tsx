"use client";

export function SiteFooter() {
  return (
    <footer className="shrink-0 border-t border-stone-200/70 bg-white/90 px-4 py-4 text-xs text-emerald-900/70 backdrop-blur-sm sm:text-sm">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-4">
        <div className="flex flex-col gap-2">
          <h2 className="text-sm font-semibold text-emerald-950 sm:text-base">
            Лицензии и данные
          </h2>
          <p>
            Данные карты:{" "}
            <a
              href="https://www.openstreetmap.org/copyright"
              target="_blank"
              rel="noreferrer"
              className="font-medium text-emerald-900 underline decoration-emerald-300/90 underline-offset-2 transition hover:text-emerald-950 hover:decoration-emerald-600"
            >
              © OpenStreetMap contributors
            </a>
            , лицензия{" "}
            <a
              href="https://opendatacommons.org/licenses/odbl/1-0/"
              target="_blank"
              rel="noreferrer"
              className="font-medium text-emerald-900 underline decoration-emerald-300/90 underline-offset-2 transition hover:text-emerald-950 hover:decoration-emerald-600"
            >
              ODbL 1.0
            </a>
            . Геокодинг:{" "}
            <a
              href="https://nominatim.org/release-docs/latest/api/Overview/#usage-policy"
              target="_blank"
              rel="noreferrer"
              className="font-medium text-emerald-900 underline decoration-emerald-300/90 underline-offset-2 transition hover:text-emerald-950 hover:decoration-emerald-600"
            >
              Nominatim
            </a>{" "}
            —{" "}
            <a
              href="https://operations.osmfoundation.org/policies/nominatim/"
              target="_blank"
              rel="noreferrer"
              className="font-medium text-emerald-900 underline decoration-emerald-300/90 underline-offset-2 transition hover:text-emerald-950 hover:decoration-emerald-600"
            >
              политика использования
            </a>
            . Маршрутизация по дорогам:{" "}
            <a
              href="https://project-osrm.org/"
              target="_blank"
              rel="noreferrer"
              className="font-medium text-emerald-900 underline decoration-emerald-300/90 underline-offset-2 transition hover:text-emerald-950 hover:decoration-emerald-600"
            >
              OSRM
            </a>{" "}
            (по умолчанию публичный сервис{" "}
            <a
              href="https://router.project-osrm.org/"
              target="_blank"
              rel="noreferrer"
              className="font-medium text-emerald-900 underline decoration-emerald-300/90 underline-offset-2 transition hover:text-emerald-950 hover:decoration-emerald-600"
            >
              router.project-osrm.org
            </a>
            ; данные маршрутов основаны на OpenStreetMap). Содержание реестров PDF принадлежит{" "}
            <a
              href="https://ecoinfo.by"
              target="_blank"
              rel="noreferrer"
              className="font-medium text-emerald-900 underline decoration-emerald-300/90 underline-offset-2 transition hover:text-emerald-950 hover:decoration-emerald-600"
            >
              ecoinfo.by
            </a>
            .
          </p>
          <p className="text-emerald-900/70">Сервис разработан Евгением Кулишом.</p>
        </div>
      </div>
    </footer>
  );
}
