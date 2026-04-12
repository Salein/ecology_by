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
    <html lang="ru" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-background font-sans text-stone-800">
        <AuthProvider>
          <div className="flex min-h-0 flex-1 flex-col">{children}</div>
        </AuthProvider>
        <footer className="shrink-0 border-t border-emerald-100/80 bg-emerald-50/50 px-4 py-3 text-center text-xs text-emerald-800/75 sm:text-sm">
          Связь с разработчиком:{" "}
          <a
            href="mailto:eug.kulish@gmail.com"
            className="font-medium text-emerald-900 underline decoration-emerald-300/90 underline-offset-2 transition hover:text-emerald-950 hover:decoration-emerald-600"
          >
            eug.kulish@gmail.com
          </a>
        </footer>
      </body>
    </html>
  );
}
