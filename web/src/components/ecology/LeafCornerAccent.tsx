import Image from "next/image";

const cornerMask: React.CSSProperties = {
  WebkitMaskImage: `
    linear-gradient(to bottom, #000 38%, transparent 78%),
    linear-gradient(to right, #000 40%, transparent 76%)
  `,
  maskImage: `
    linear-gradient(to bottom, #000 38%, transparent 78%),
    linear-gradient(to right, #000 40%, transparent 76%)
  `,
  WebkitMaskComposite: "source-in",
  maskComposite: "intersect",
};

/**
 * Фрагмент обоев с GoodFon (ветка, листья): исходная страница
 * https://www.goodfon.ru/nature/wallpaper-vetka-derevo-zelenye-listya.html
 * — файл сохранён локально для оформления угла; при публикации учитывайте условия GoodFon.
 */
export function LeafCornerAccent() {
  return (
    <div
      className="pointer-events-none absolute top-0 left-0 z-0 h-[min(200px,40vw)] w-[min(300px,78vw)] -translate-x-1 -translate-y-1 overflow-hidden rounded-br-3xl select-none sm:h-[230px] sm:w-[340px] sm:-translate-x-2 sm:-translate-y-2"
      aria-hidden
    >
      <div className="relative h-full w-full" style={cornerMask}>
        <Image
          src="/goodfon-leaves.webp"
          alt=""
          fill
          sizes="(max-width: 640px) 78vw, 340px"
          className="object-cover object-left object-top opacity-80"
          priority
        />
      </div>
    </div>
  );
}
