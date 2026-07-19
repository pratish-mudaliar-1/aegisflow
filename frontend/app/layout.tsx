import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "AegisFlow — AI Orchestration Command Center",
  description:
    "Enterprise-grade LangGraph AI orchestration workspace with real-time state graph visualization, live telemetry feeds, and human-in-the-loop governance controls.",
  keywords: ["AI orchestration", "LangGraph", "enterprise AI", "HITL", "AegisFlow"],
  authors: [{ name: "AegisFlow Team" }],
  robots: "noindex, nofollow",
  openGraph: {
    title: "AegisFlow — AI Orchestration Command Center",
    description: "Enterprise LangGraph orchestration workspace with real-time observability.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body className="bg-zinc-950 text-zinc-100 antialiased overflow-hidden">
        {children}
      </body>
    </html>
  );
}
