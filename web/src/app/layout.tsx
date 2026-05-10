import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { AppProviders } from "@/components/AppProviders";
import { SiteFooter } from "@/components/SiteFooter";
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
      <body className="flex min-h-full flex-col bg-background font-sans text-stone-800">
        <AppProviders>
          <div className="flex min-h-0 flex-1 flex-col">{children}</div>
          <SiteFooter />
        </AppProviders>
      </body>
    </html>
  );
}
