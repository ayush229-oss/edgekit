import "./globals.css";
import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";

export const metadata: Metadata = {
  title: "Edgekit — Backtest any strategy, any market",
  description: "No-code visual strategy builder. Find your trader's edge with sliders, not code.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider
      appearance={{
        variables: {
          colorPrimary:    "#0B6E4F",
          colorBackground: "#FFFFFF",
          colorText:       "#0A0A0A",
          colorTextSecondary: "#86868B",
          borderRadius:    "10px",
          fontFamily:      "Inter, system-ui, sans-serif",
        },
      }}
    >
      <html lang="en">
        <body className="min-h-screen bg-paper text-ink antialiased">
          {children}
        </body>
      </html>
    </ClerkProvider>
  );
}
