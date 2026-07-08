import Link from "next/link";
import { ArrowRight, CirclePlay, Leaf, Star } from "lucide-react";

const avatars = ["A", "M", "J", "P"];

export default function HeroCopy() {
  return (
    <section className="relative z-10 max-w-[650px]">
      <div className="mb-[30px] inline-flex h-[38px] items-center gap-2 rounded-full border border-[#C9D1A7] bg-[#FFF9EC]/76 px-[18px] text-[15px] font-semibold tracking-[0.01em] text-[#526736] shadow-sm">
        <Leaf className="h-4 w-4 fill-[#738045] text-[#738045]" />
        Your quiet job scout
      </div>

      <h1 className="font-serif text-[4.5rem] font-bold leading-[0.96] tracking-[-0.045em] text-[#1F281B] sm:text-[5rem] lg:text-[82px] 2xl:text-[88px]">
        A tiny scout
        <br />
        for the roles you
        <br />
        would have{" "}
        <span className="relative inline-block italic text-[#526736]">
          missed.
          <span className="absolute -bottom-1 left-1 h-2 w-full rounded-[50%] border-b-[3px] border-[#C99635]" />
        </span>
      </h1>

      <p className="mt-[26px] max-w-[575px] text-[19px] font-normal leading-[1.62] text-[#5F665C]">
        Nori quietly watches company career pages and ATS boards so you don&apos;t have to. Get fresh, direct-apply roles as clean notes&mdash;every single day.
      </p>

      <div className="mt-8 flex flex-col gap-[18px] sm:flex-row">
        <Link href="/jobs" className="inline-flex h-[58px] items-center justify-center gap-2.5 rounded-[14px] bg-[#526736] px-[30px] text-base font-bold text-[#FFF9EC] shadow-[0_12px_26px_rgba(38,58,34,0.22)] transition hover:bg-[#43552C]">
          <CirclePlay className="h-[18px] w-[18px]" />
          See today&apos;s notes
        </Link>
        <Link href="#how-it-works" className="inline-flex h-[58px] items-center justify-center gap-2.5 rounded-[14px] border border-[#CDBF9A] bg-[#FFF9EC]/70 px-7 text-base font-semibold text-[#1F281B] shadow-sm transition hover:bg-white">
          <CirclePlay className="h-[18px] w-[18px]" />
          How Nori works
        </Link>
      </div>

      <div className="mt-7 flex flex-wrap items-center gap-3.5">
        <div className="flex -space-x-2.5">
          {avatars.map((avatar, index) => (
            <span key={avatar} className="grid h-[34px] w-[34px] place-items-center rounded-full border-2 border-[#FFF8EA] bg-[#D9C9A0] text-xs font-black text-[#4E432C] shadow-sm" style={{ backgroundColor: ["#D2B99A", "#B9C1A2", "#D7A585", "#C9B08A"][index] }}>
              {avatar}
            </span>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <div className="flex text-[#C99022]">
            {Array.from({ length: 5 }).map((_, index) => (
              <Star key={index} className="h-4 w-4 fill-current" />
            ))}
          </div>
          <p className="text-sm font-medium text-[#5F665C]">Loved by 2,000+ job seekers</p>
        </div>
      </div>

      <ArrowRight className="absolute right-2 top-44 hidden h-6 w-6 -rotate-12 text-[#C99022] lg:block" />
    </section>
  );
}
