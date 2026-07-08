import type { ReactNode } from "react";
import Image from "next/image";

interface HeroBackgroundProps {
  children: ReactNode;
}

function DeskDecor() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      <Image src="/nori-assets/desk-paper-texture.png" alt="" aria-hidden="true" fill sizes="100vw" className="object-cover opacity-95" />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_12%_12%,rgba(255,255,255,0.58),transparent_28%),radial-gradient(circle_at_78%_18%,rgba(222,191,123,0.18),transparent_30%),linear-gradient(115deg,rgba(253,246,231,0.52)_0%,rgba(247,233,204,0.44)_52%,rgba(239,221,190,0.56)_100%)]" />
      <div className="absolute inset-0 opacity-[0.12] mix-blend-multiply [background-image:linear-gradient(rgba(115,88,45,0.08)_1px,transparent_1px),linear-gradient(90deg,rgba(115,88,45,0.06)_1px,transparent_1px)] [background-size:42px_42px]" />
      <div className="absolute -left-10 top-0 h-full w-36 rotate-[-7deg] border-r border-[#DEC99F]/70 bg-[#FFF5DE]/70 shadow-[16px_0_45px_rgba(94,70,37,0.08)]">
        <div className="mt-6 h-full bg-[repeating-linear-gradient(to_bottom,transparent_0,transparent_31px,rgba(123,94,54,0.13)_32px)]" />
      </div>
    </div>
  );
}

export default function HeroBackground({ children }: HeroBackgroundProps) {
  return (
    <main className="relative min-h-screen overflow-hidden bg-[#F7E9CC] text-[#221D16]">
      <DeskDecor />
      <div className="relative mx-auto min-h-screen w-full max-w-[1720px] px-5 py-4 sm:px-8 lg:px-12">
        {children}
      </div>
    </main>
  );
}
