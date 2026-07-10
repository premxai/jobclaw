import type { Metadata } from "next";
import { Fraunces, Inter } from "next/font/google";
import localFont from "next/font/local";
import FeedbackButton from "@/components/FeedbackButton";
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

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-fraunces",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://norinote.xyz"),
  title: {
    default: "Nori Note - Fresh tech jobs, neatly noted",
    template: "%s - Nori Note",
  },
  description:
    "Nori searches across the internet for fresh tech jobs, notes the good ones, and keeps your job hunt organized.",
  keywords: ["Nori Note", "jobs", "tech jobs", "AI jobs", "software engineer", "new grad", "job board"],
  icons: {
    icon: "/nori-assets/nori-mark.png",
    shortcut: "/nori-assets/nori-mark.png",
    apple: "/nori-assets/nori-mark.png",
  },
  openGraph: {
    title: "Nori Note - Fresh tech jobs, neatly noted",
    description: "Thousands of companies monitored. Fresh roles every few hours, direct links, and an organized tracker.",
    type: "website",
    url: "https://norinote.xyz",
    siteName: "Nori Note",
  },
  twitter: {
    card: "summary",
    title: "Nori Note - Fresh tech jobs, neatly noted",
    description: "Nori searches the internet and notes fresh roles for your job hunt.",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} ${inter.variable} ${fraunces.variable} antialiased`}>
        {children}
        <FeedbackButton />
      </body>
    </html>
  );
}
