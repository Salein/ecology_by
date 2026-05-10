import Image from "next/image";

/**
 * Фрагмент обоев с GoodFon (ветка, листья): исходная страница
 * https://www.goodfon.ru/nature/wallpaper-vetka-derevo-zelenye-listya.html
 * — файл сохранён локально для оформления угла; при публикации учитывайте условия GoodFon.
 */
export function LeafCornerAccent() {
  return (
    <div
      className="pointer-events-none absolute top-0 left-0 z-0 h-[min(220px,44vw)] w-[min(360px,88vw)] -translate-x-1 -translate-y-1 overflow-hidden rounded-br-[2.25rem] select-none sm:h-[250px] sm:w-[420px] sm:rounded-br-[3rem] sm:-translate-x-2 sm:-translate-y-2"
      aria-hidden
    >
      <div className="relative isolate h-full w-full">
        <Image
          src="/goodfon-leaves.webp"
          alt=""
          fill
          sizes="(max-width: 640px) 78vw, 340px"
          className="object-cover object-left object-top"
          priority
        />
        {/* Плавное растворение в фон страницы (не в белый — иначе виден шов с #f3f7f4) */}
        <div
          className="pointer-events-none absolute inset-y-0 right-0 z-[1] w-[72%]"
          style={{
            background:
              "linear-gradient(to right, transparent 0%, color-mix(in srgb, var(--background) 35%, transparent) 42%, var(--background) 100%)",
          }}
        />
        <div
          className="pointer-events-none absolute inset-x-0 bottom-0 z-[1] h-[82%]"
          style={{
            background:
              "linear-gradient(to bottom, transparent 0%, color-mix(in srgb, var(--background) 6%, transparent) 22%, color-mix(in srgb, var(--background) 38%, transparent) 45%, color-mix(in srgb, var(--background) 82%, transparent) 72%, var(--background) 100%)",
          }}
        />
        <div className="pointer-events-none absolute -right-10 -bottom-10 z-[1] h-44 w-44 rounded-full bg-background/95 blur-2xl sm:h-56 sm:w-56" />
      </div>
    </div>
  );
}
