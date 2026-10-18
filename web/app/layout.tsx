import type { Metadata, Viewport } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";

import { SandboxBanner } from "@/components/layout/sandbox-banner";
import { AppProviders } from "@/components/providers/app-providers";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "StudyRoute", template: "%s | StudyRoute" },
  description:
    "Pay tuition and living costs abroad from Bangladesh with clear costs, a safe checklist and a human in control. Sandbox, synthetic data.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f7f7f8" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0a0b" },
  ],
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${GeistSans.variable} ${GeistMono.variable}`}
    >
      <body className="min-h-svh font-sans">
        <SandboxBanner />
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
