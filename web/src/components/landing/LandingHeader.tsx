import Link from "next/link";
import NoriMark from "./NoriMark";

export default function LandingHeader() {
  return (
    <header className="relative z-20 mx-auto mt-3 flex h-[76px] max-w-[1640px] items-center justify-between rounded-[26px] border border-[#E7D7B7] bg-[#FFF9EC]/88 px-5 shadow-[0_18px_48px_rgba(83,61,28,0.10)] backdrop-blur-md sm:px-8 lg:px-10">
      <Link href="/" className="flex items-center gap-3" aria-label="Nori home">
        <NoriMark />
        <span className="font-serif text-[34px] font-bold leading-none tracking-[-0.04em] text-[#1F281B]">Nori</span>
      </Link>

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
