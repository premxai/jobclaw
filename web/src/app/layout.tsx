import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  display: "swap",
});

const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://norinote.xyz"),
  title: {
    default: "norinote — Fresh tech jobs, less noise",
    template: "%s · norinote",
  },
  description:
    "Fresh US tech roles from thousands of companies, updated every few hours. AI/ML, SWE, Data, Product, and New Grad — direct links, less noise.",
  keywords: ["norinote", "jobs", "tech jobs", "AI jobs", "software engineer", "new grad", "job board"],
  openGraph: {
    title: "norinote — Fresh tech jobs, less noise",
    description: "Thousands of companies monitored. Fresh roles every few hours — direct links, less noise.",
    type: "website",
    url: "https://norinote.xyz",
    siteName: "norinote",
  },
  twitter: {
    card: "summary",
    title: "norinote — Fresh tech jobs, less noise",
    description: "Fresh US tech roles every few hours. Direct links, less noise.",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>{children}</body>
    </html>
  );
}
