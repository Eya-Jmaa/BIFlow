import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { Providers } from "@/components/providers";
import "./globals.css";

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "BIFlow — Multi-agent BI",
  description:
    "Raw data to an audited dashboard: seven agents profile, clean, model, measure, analyse and explain.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} h-full`}>
      <body className="app-canvas min-h-full font-sans">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
