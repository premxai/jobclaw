import Link from "next/link";
import Image from "next/image";
import { ArrowRight, Sparkles } from "lucide-react";

const jobs = [
  {
    company: "OpenAI",
    logo: "AI",
    title: "Research Engineer",
    found: "Found 3m ago",
    tags: ["AI/ML", "Remote", "Direct apply"],
    tone: "bg-[#202A2C] text-white",
    rotate: "-rotate-[1.2deg]",
  },
  {
    company: "Stripe",
    logo: "S",
    title: "Backend Engineer, AI Platform",
    found: "Found 12m ago",
    tags: ["SWE", "Remote", "Direct apply"],
    tone: "bg-gradient-to-br from-[#7B65FF] to-[#513BD6] text-white",
    rotate: "rotate-[0.8deg]",
  },
  {
    company: "Airbnb",
    logo: "A",
    title: "Data Scientist",
    found: "Found 24m ago",
    tags: ["Data", "Hybrid", "Direct apply"],
    tone: "bg-gradient-to-br from-[#FA6B72] to-[#E94462] text-white",
    rotate: "rotate-[1.1deg]",
  },
];

const paperBackground = {
  backgroundImage: "linear-gradient(rgba(255, 246, 226, 0.72), rgba(255, 246, 226, 0.72)), url('/nori-assets/paper-texture.png')",
  backgroundSize: "cover",
};

function PaperClip({ className = "" }: { className?: string }) {
  return (
    <span className={`pointer-events-none absolute h-24 w-12 rotate-[24deg] rounded-full border-[5px] border-[#B98935] opacity-90 shadow-sm ${className}`}>
      <span className="absolute left-2 top-3 h-16 w-6 rounded-full border-[4px] border-[#D0A257]" />
    </span>
  );
}

function JobNote({ job }: { job: (typeof jobs)[number] }) {
  return (
    <article
      className={`relative h-[300px] rounded-lg border border-[#E5D2A8] bg-[#FFF7E5] p-7 shadow-[0_16px_28px_rgba(70,45,16,0.14),inset_0_1px_0_rgba(255,255,255,0.8)] [clip-path:polygon(0_2%,100%_0,98%_97%,82%_99%,68%_97%,53%_100%,36%_98%,18%_100%,2%_97%)] ${job.rotate}`}
      style={paperBackground}
    >
      <div className={`mb-[22px] grid h-12 w-12 place-items-center rounded-xl text-lg font-black shadow-sm ${job.tone}`}>{job.logo}</div>
      <h3 className="font-serif text-[28px] font-bold leading-[1.05] tracking-[-0.035em] text-[#1F281B]">{job.company}</h3>
      <p className="mt-1.5 min-h-[44px] text-base font-medium leading-[1.35] text-[#30352C]">{job.title}</p>
      <p className="mt-4 flex items-center gap-2 text-sm font-medium text-[#66705F]">
        <span className="h-2.5 w-2.5 rounded-full bg-[#526736]" />
        {job.found}
      </p>
      <div className="mt-[18px] flex flex-wrap gap-2">
        {job.tags.map((tag) => (
          <span key={tag} className="inline-flex h-7 items-center rounded-full border border-[#E1D2AD] bg-[#F7EED7] px-3 text-xs font-semibold text-[#4A513C]">
            {tag}
          </span>
        ))}
      </div>
      <Link href="/jobs" className="absolute bottom-[22px] right-6 text-[#526736]" aria-label={`Apply to ${job.title} at ${job.company}`}>
        <ArrowRight className="h-5 w-5" />
      </Link>
    </article>
  );
}

export default function NotesBoard() {
  return (
    <section className="relative z-10 mx-auto w-full max-w-[940px] py-2 lg:py-0">
      <span className="pointer-events-none absolute -right-[72px] bottom-[120px] z-20 hidden h-[170px] w-[170px] opacity-100 drop-shadow-[0_18px_28px_rgba(86,55,25,0.2)] xl:block">
        <Image src="/nori-assets/coffee-cup.png" alt="" aria-hidden="true" fill sizes="170px" className="object-contain" />
      </span>
      <span className="pointer-events-none absolute -right-[34px] top-[120px] z-20 hidden h-[220px] w-[176px] opacity-80 drop-shadow-[0_12px_18px_rgba(92,68,35,0.12)] xl:block">
        <Image src="/nori-assets/dried-flowers.png" alt="" aria-hidden="true" fill sizes="176px" className="object-contain" />
      </span>
      <span className="pointer-events-none absolute bottom-6 right-20 z-20 hidden h-[70px] w-[280px] -rotate-[4deg] opacity-95 drop-shadow-[0_12px_16px_rgba(78,50,21,0.18)] xl:block">
        <Image src="/nori-assets/fountain-pen.png" alt="" aria-hidden="true" fill sizes="280px" className="object-contain" />
      </span>
      <div
        className="relative min-h-[560px] overflow-visible rounded-[34px] border border-[rgba(38,58,34,0.26)] bg-[#596344] bg-cover bg-center p-[34px] shadow-[0_24px_60px_rgba(60,42,16,0.18),inset_0_0_35px_rgba(25,36,20,0.32)]"
        style={{
          backgroundImage:
            "linear-gradient(135deg, rgba(68, 78, 43, 0.46), rgba(103, 114, 78, 0.32)), url('/nori-assets/notebook-texture.png')",
        }}
      >
        <span className="absolute -right-2 top-10 h-36 w-5 rounded-r-2xl bg-[#B99A61] shadow-inner" />
        <span className="absolute -left-2 bottom-10 h-24 w-5 rounded-l-2xl bg-[#B99A61] shadow-inner" />
        <div className="absolute inset-4 rounded-[28px] border border-white/10 bg-[radial-gradient(circle_at_24%_12%,rgba(255,255,255,0.12),transparent_28%),linear-gradient(135deg,rgba(117,128,94,0.18),rgba(67,83,47,0.18))]" />

        <div className="absolute inset-x-[38px] bottom-[45px] top-10 rotate-[-1deg] rounded border border-[#E2D0A8] bg-[#F8ECD6] shadow-[0_8px_20px_rgba(50,32,12,0.12)]" style={paperBackground} />
        <div className="absolute inset-x-[48px] bottom-[56px] top-[78px] rotate-[1deg] rounded border border-[#E2D0A8] bg-[#F8ECD6] shadow-[0_8px_20px_rgba(50,32,12,0.10)]" style={paperBackground} />

        <div className="absolute left-1/2 top-7 z-10 flex h-16 w-[min(520px,80%)] -translate-x-1/2 -rotate-1 items-center justify-center gap-3 border border-[#DEC799] bg-[#FFF5DF] px-8 text-center shadow-[0_8px_18px_rgba(60,42,16,0.12)] [clip-path:polygon(2%_0,100%_4%,98%_100%,0_94%)]" style={paperBackground}>
          <h2 className="font-serif text-[30px] font-semibold tracking-[-0.035em] text-[#1F281B]">Today&apos;s Notes from Nori</h2>
          <span className="relative h-8 w-8 scale-[1.55]">
            <Image src="/nori-assets/nori-mark.png" alt="" aria-hidden="true" fill sizes="36px" className="object-contain" />
          </span>
          <Sparkles className="h-5 w-5 text-[#C99022]" />
        </div>

        <PaperClip className="left-28 top-8 hidden scale-[0.6] -rotate-12 lg:block" />
        <PaperClip className="right-2 top-[132px] hidden scale-[0.56] rotate-[10deg] lg:block" />
        <span className="absolute left-[48%] top-28 z-20 hidden h-7 w-7 rounded-full bg-[#C99A43] shadow-[0_8px_12px_rgba(62,44,22,0.22)] lg:block" />
        <span className="absolute left-[44%] top-[5.75rem] z-10 hidden h-9 w-32 rotate-3 bg-[#9E9B61]/70 lg:block" />

        <div className="relative z-10 grid gap-6 px-0 pt-28 lg:grid-cols-3 lg:px-[22px]">
          {jobs.map((job) => (
            <JobNote key={job.company} job={job} />
          ))}
        </div>

        <div className="absolute bottom-[18px] left-1/4 z-10 hidden h-[72px] w-[270px] -rotate-2 border border-[#D9C296] bg-[#FFF5DF] px-5 py-3.5 text-base italic leading-6 text-[#5F665C] shadow-[0_8px_18px_rgba(60,42,16,0.12)] sm:block" style={paperBackground}>
          New notes arrive
          <br />
          while you focus.
        </div>
      </div>
    </section>
  );
}
