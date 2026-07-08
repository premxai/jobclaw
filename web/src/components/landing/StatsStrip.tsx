import { Clock3, Search, ShieldCheck, Sparkles } from "lucide-react";

const stats = [
  { icon: Search, value: "31K+", label: "sources watched", tone: "text-[#6D7542]" },
  { icon: Sparkles, value: "128", label: "new roles today", tone: "text-[#C99022]" },
  { icon: ShieldCheck, value: "94%", label: "direct apply roles", tone: "text-[#6D7542]" },
  { icon: Clock3, value: "5 min", label: "scan cycle", tone: "text-[#C99022]" },
];

export default function StatsStrip() {
  return (
    <section className="relative z-10 min-h-[104px] rounded-[22px] border border-[#E7D7B7] bg-[#FFF9EC]/88 px-5 py-4 shadow-[0_12px_28px_rgba(70,45,16,0.08)] backdrop-blur-xl lg:px-12">
      <div className="grid h-full gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map(({ icon: Icon, value, label, tone }, index) => (
          <div key={label} className="relative flex items-center justify-center gap-[18px] py-2">
            {index > 0 && <span className="absolute left-0 top-1/2 hidden h-14 w-px -translate-y-1/2 bg-[#D7BE8A] lg:block" />}
            <span className={`grid h-[52px] w-[52px] place-items-center rounded-full bg-[#EEF1DD] ${tone}`}>
              <Icon className="h-6 w-6" />
            </span>
            <span>
              <span className="block font-serif text-[31px] font-bold leading-none tracking-[-0.04em] text-[#1F281B]">{value}</span>
              <span className="mt-1 block text-[13px] font-medium leading-[1.3] text-[#5F665C]">{label}</span>
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
