import React from "react";
import type { Metadata, Viewport } from "next";
import { Providers } from "@/components/features/providers";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: {
    default: "Vision Query AI",
    template: "%s | Vision Query AI",
  },
  description: "Enterprise GPU-powered Vision Analytics Platform",
  manifest: "/manifest.json",
  icons: {
    icon: "/favicon.ico",
  },
};

export const viewport: Viewport = {
  themeColor: "#76b900",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-background font-sans antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
