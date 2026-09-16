import type { Metadata } from "next";
import "@fontsource-variable/bricolage-grotesque";
import "@fontsource-variable/dm-sans";
import "@fontsource-variable/manrope";

import "./globals.css";
import { AppProvider } from "./components/app-provider";

export const metadata: Metadata = {
  title: "Focus Tiger",
  description: "Turn small actions into lasting habits",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body><AppProvider>{children}</AppProvider></body>
    </html>
  );
}
