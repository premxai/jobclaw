import type { Metadata } from "next";
import { Lexend } from "next/font/google";
import "./globals.css";

const lexend = Lexend({
  subsets: ["latin"],
  variable: "--font-lexend",
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
    <html lang="en" className="dark">
      <body className={`${lexend.variable} font-sans antialiased`}>
        {children}
      </body>
    </html>
  );
}
