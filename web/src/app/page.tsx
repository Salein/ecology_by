import { LeafCornerAccent } from "@/components/ecology/LeafCornerAccent";
import { WelcomePage } from "@/components/auth/WelcomePage";

export default function Home() {
  return (
    <div className="relative min-h-full flex-1 overflow-x-hidden">
      <LeafCornerAccent />
      <section className="mx-auto w-full max-w-5xl px-4 pt-10 sm:px-6 sm:pt-14">
        <div className="rounded-3xl border border-emerald-100/90 bg-white/95 p-6 shadow-sm shadow-emerald-900/5 sm:p-8">
          <h1 className="text-3xl font-semibold tracking-tight text-emerald-950 sm:text-4xl">
            Экология Беларуси: поиск объектов обращения с отходами
          </h1>
          <p className="mt-3 max-w-3xl text-base leading-relaxed text-emerald-900/70">
            Сервис помогает находить объекты по виду отходов, адресу и расстоянию до выбранной точки на карте.
            Данные формируются из официальных реестров PDF, а геолокация объектов уточняется и кэшируется для
            ускорения поиска.
          </p>
          <div className="mt-5 grid gap-4 text-sm text-emerald-900/75 sm:grid-cols-3">
            <div className="rounded-2xl border border-emerald-100/90 bg-emerald-50/60 px-4 py-3">
              <p className="font-semibold text-emerald-950">Что умеет сервис</p>
              <p className="mt-1">Поиск по кодам и видам отходов, адресам и ближайшим объектам.</p>
            </div>
            <div className="rounded-2xl border border-emerald-100/90 bg-emerald-50/60 px-4 py-3">
              <p className="font-semibold text-emerald-950">Источник данных</p>
              <p className="mt-1">Реестры объектов по использованию отходов и карты OpenStreetMap.</p>
            </div>
            <div className="rounded-2xl border border-emerald-100/90 bg-emerald-50/60 px-4 py-3">
              <p className="font-semibold text-emerald-950">Контакты</p>
              <p className="mt-1">
                Вопросы и предложения:{" "}
                <a
                  href="mailto:eug.kulish@gmail.com"
                  className="font-medium text-emerald-900 underline decoration-emerald-300/90 underline-offset-2 transition hover:text-emerald-950 hover:decoration-emerald-600"
                >
                  eug.kulish@gmail.com
                </a>
              </p>
            </div>
          </div>
        </div>
      </section>
      <WelcomePage />
    </div>
  );
}
