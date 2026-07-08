import Link from "next/link";
import { ChevronDown } from "lucide-react";
import NoriMark from "./NoriMark";

const navItems = [
  ["How it works", "#how-it-works"],
  ["Features", "#features"],
  ["For teams", "#teams"],
  ["Pricing", "#pricing"],
];

export default function LandingHeader() {
  return (
    <header className="relative z-20 flex h-[72px] items-center justify-between border-b border-[#E7D7B7] bg-[#FFF9EC]/86 px-5 shadow-[0_10px_35px_rgba(83,61,28,0.06)] backdrop-blur-md sm:px-8 lg:px-10">
      <Link href="/" className="flex items-center gap-3" aria-label="Nori home">
        <NoriMark />
        <span className="font-serif text-[34px] font-bold leading-none tracking-[-0.04em] text-[#1F281B]">Nori</span>
      </Link>

      <nav className="hidden items-center gap-[42px] text-[15px] font-medium text-[#1F281B] lg:flex">
        {navItems.map(([label, href]) => (
          <Link key={label} href={href} className="transition hover:text-[#5C6831]">
            {label}
          </Link>
        ))}
        <Link href="#resources" className="inline-flex items-center gap-1 transition hover:text-[#5C6831]">
          Resources
          <ChevronDown className="h-4 w-4" />
        </Link>
      </nav>

      <div className="flex items-center gap-2 sm:gap-4">
        <Link href="/profile" className="hidden h-11 items-center px-[18px] text-sm font-semibold text-[#1F281B] transition hover:text-[#526736] sm:inline-flex">
          Login
        </Link>
        <Link href="/profile" className="inline-flex h-[46px] items-center rounded-[14px] bg-[#526736] px-[26px] text-sm font-bold text-[#FFF9EC] shadow-[0_8px_18px_rgba(38,58,34,0.18)] transition hover:bg-[#43552C]">
          Sign up
        </Link>
      </div>
    </header>
  );
}
