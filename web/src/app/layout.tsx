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
  title: "JobClaw — Track Every Tech Job. Automatically.",
  description:
    "11,800+ companies monitored 24/7. Find AI/ML, SWE, Data, and New Grad jobs from Greenhouse, Lever, Workday, LinkedIn, and more.",
  keywords: ["jobs", "tech jobs", "AI jobs", "software engineer", "new grad", "job board"],
  openGraph: {
    title: "JobClaw — Track Every Tech Job",
    description: "11,800+ companies monitored. Updated every hour.",
    type: "website",
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
