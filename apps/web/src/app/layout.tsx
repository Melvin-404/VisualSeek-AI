/**
 * Root Layout Component.
 *
 * This is the main HTML layout wrapper for the Next.js frontend application.
 */

import React from "react";

export const metadata = {
  title: "Vision Query AI",
  description: "Enterprise-grade GPU-powered Vision Analytics Platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <main>{children}</main>
      </body>
    </html>
  );
}
