import { ArrowRight } from "lucide-react";

const features = [
  {
    number: "01",
    title: "Quiet monitoring",
    text: "Nori checks thousands of company career pages and ATS boards, 24/7, so you can focus on what matters.",
    sketch: "telescope",
  },
  {
    number: "02",
    title: "Clean notes",
    text: "We turn noise into clarity. Only fresh, relevant, direct-apply roles delivered as beautiful daily notes.",
    sketch: "notepad",
  },
  {
    number: "03",
    title: "Fast apply tracking",
    text: "Save, apply, and track progress in one place. Know what's done and what's next.",
    sketch: "checklist",
  },
];

function Sketch({ type }: { type: string }) {
  if (type === "telescope") {
    return (
      <svg viewBox="0 0 180 120" className="h-[120px] w-[120px] text-[#756B4C]" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M25 54 118 25l11 34-92 30z" />
        <path d="M104 30l18-6 14 41-18 6" />
        <path d="M53 84 34 113M82 75l10 38M61 81l18 32" />
        <path d="M44 49c16 9 22 24 17 42" />
      </svg>
    );
  }

  if (type === "notepad") {
    return (
      <svg viewBox="0 0 170 130" className="h-[120px] w-[120px] text-[#756B4C]" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M50 12h70l15 94-82 12z" />
        <path d="M62 32h52M65 50h48M68 68h44M71 86h36" />
        <path d="M60 12v16M78 12v16M96 12v16M114 12v16" />
        <path d="M125 78 151 104M143 72l-25 34" />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 170 130" className="h-[120px] w-[120px] text-[#756B4C]" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M45 12h78l11 104H57z" />
      <path d="M68 38h42M68 61h44M68 84h38" />
      <path d="m52 35 6 6 12-15M53 58l6 6 12-15M55 82l6 6 12-15" />
      <path d="M121 48c16 6 22 16 25 30M132 68c11-14 19-17 28-17" />
    </svg>
  );
}

export default function FeatureCards() {
  return (
    <section id="features" className="relative z-10 mt-[34px] grid gap-7 pb-6 lg:grid-cols-3">
      {features.map((feature) => (
        <article key={feature.title} className="relative flex min-h-[188px] items-center overflow-hidden rounded-[20px] border border-[#E7D7B7] bg-[#FFF9EC]/82 px-8 py-7 shadow-[0_10px_24px_rgba(70,45,16,0.07)] backdrop-blur lg:px-[34px]">
          <div className="grid w-full items-center gap-7 sm:grid-cols-[120px_1fr]">
            <div className="relative">
              <Sketch type={feature.sketch} />
            </div>
            <div>
              <h3 className="mb-2.5 font-serif text-[26px] font-bold leading-[1.1] tracking-[-0.04em] text-[#1F281B]">{feature.title}</h3>
              <p className="max-w-[310px] text-[14.5px] font-medium leading-[1.5] text-[#5F665C]">{feature.text}</p>
            </div>
          </div>
          <span className="absolute right-7 top-6 grid h-[26px] w-[38px] place-items-center rounded-[9px] bg-[#526736] text-xs font-bold text-[#FFF9EC]">{feature.number}</span>
          <ArrowRight className="absolute bottom-6 right-7 h-5 w-5 text-[#C99022]" />
        </article>
      ))}
    </section>
  );
}
