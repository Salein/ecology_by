import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { AuthProvider } from "@/context/AuthContext";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin", "cyrillic"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Экология — объекты обращения с отходами",
  description: "Поиск объектов, карта OpenStreetMap, API на Python",
  /* Иконка вкладки: PNG с подборки «Листья зелёные» (png.klev.club). Условия: https://png.klev.club/349-listja-zelenye.html */
  icons: {
    icon: [{ url: "/icon.png", type: "image/png" }],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru" className={`${geistSans.variable} ${geistMono.variable} h-full bg-white antialiased`}>
      <body className="flex min-h-full flex-col bg-white font-sans text-stone-800">
        <AuthProvider>
          <div className="flex min-h-0 flex-1 flex-col bg-white">{children}</div>
        </AuthProvider>
        <footer className="shrink-0 border-t border-emerald-100/80 bg-white px-4 py-4 text-xs text-emerald-800/75 sm:text-sm">
          <div className="mx-auto flex w-full max-w-6xl flex-col gap-2">
            <h2 className="text-sm font-semibold text-emerald-950 sm:text-base">Лицензии и данные</h2>
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
              . Содержание реестров PDF принадлежит{" "}
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
            <p>Сервис разработан Евгением Кулишом.</p>
          </div>
        </footer>
      </body>
    </html>
  );
}
