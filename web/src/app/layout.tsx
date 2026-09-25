import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";

import { MarketDataProvider } from "@/components/MarketDataContext";
import { TickerTape } from "@/components/TickerTape";
import { TopBar } from "@/components/TopBar";
import { WatchlistProvider } from "@/components/WatchlistContext";

import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains" });

export const metadata: Metadata = {
  title: "Realtor Mogul",
  description: "Real-estate investment terminal: underwrite, track and rank properties.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable}`}>
      <body>
        <MarketDataProvider>
          <WatchlistProvider>
            <div className="shell">
              <TopBar />
              <TickerTape />
              {children}
            </div>
          </WatchlistProvider>
        </MarketDataProvider>
      </body>
    </html>
  );
}
