import { ArrowRight } from "lucide-react";

import Badge from "./Badge";
import type { BoardJob } from "@/lib/job-board";

interface JobRowProps {
  job: BoardJob;
}

function locationTone(location: string): "neutral" | "remote" | "hybrid" {
  const normalized = location.toLowerCase();
  if (normalized.includes("hybrid")) return "hybrid";
  if (normalized.includes("remote")) return "remote";
  return "neutral";
}

export default function JobRow({ job }: JobRowProps) {
  return (
    <article className="group grid h-[var(--job-board-row-height)] grid-cols-[minmax(0,1fr)_auto] items-center gap-3 overflow-hidden border-b border-[rgba(139,94,52,0.15)] px-4 py-1 transition-colors duration-200 last:border-b-0 hover:bg-[#FFF8EC] sm:px-5">
      <div className="min-w-0">
        <div className="flex min-w-0 items-center gap-2">
          <h2 className="truncate text-[13px] font-semibold leading-tight tracking-tight text-black sm:text-sm">
            {job.title}
          </h2>
        </div>
        <p className="mt-0.5 truncate text-[10.5px] font-medium leading-3 text-[#6B6B6B] sm:text-[11px]">
          {job.description}
        </p>
      </div>

      <div className="flex min-w-0 items-center gap-2 justify-end">
        <div className="flex min-w-0 flex-nowrap items-center gap-2">
          <Badge tone={locationTone(job.location)} icon="location" className="max-w-[104px] truncate sm:max-w-[210px]">
            {job.location}
          </Badge>
        </div>

        <a
          href={job.applicationUrl}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`Apply for ${job.title}`}
          className="ml-auto inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-[#E8CFA8] bg-[#FFFEFB] text-[#171717] transition-all duration-200 hover:-translate-y-0.5 hover:bg-[#171717] hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#171717]"
        >
          <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" aria-hidden="true" />
        </a>
      </div>
    </article>
  );
}
