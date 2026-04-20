import Image from "next/image";

/**
 * Фрагмент обоев с GoodFon (ветка, листья): исходная страница
 * https://www.goodfon.ru/nature/wallpaper-vetka-derevo-zelenye-listya.html
 * — файл сохранён локально для оформления угла; при публикации учитывайте условия GoodFon.
 */
export function LeafCornerAccent() {
  return (
    <div
      className="pointer-events-none absolute top-0 left-0 z-0 h-[min(220px,44vw)] w-[min(360px,88vw)] -translate-x-1 -translate-y-1 overflow-hidden select-none sm:h-[250px] sm:w-[420px] sm:-translate-x-2 sm:-translate-y-2"
      aria-hidden
    >
      <div className="relative h-full w-full">
        <Image
          src="/goodfon-leaves.webp"
          alt=""
          fill
          sizes="(max-width: 640px) 78vw, 340px"
          className="object-cover object-left object-top"
          priority
        />
        <div className="pointer-events-none absolute inset-y-0 right-0 w-[62%] bg-gradient-to-r from-transparent via-white/60 to-white" />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[56%] bg-gradient-to-b from-transparent via-white/60 to-white" />
        <div className="pointer-events-none absolute -right-8 -bottom-8 h-40 w-40 rounded-full bg-white/85 blur-2xl sm:h-52 sm:w-52" />
      </div>
    </div>
  );
}
