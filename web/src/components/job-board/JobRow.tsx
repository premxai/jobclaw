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
    <article className="group grid h-16 grid-cols-[minmax(0,1fr)_auto] items-center gap-4 border-b border-[rgba(139,94,52,0.15)] px-5 transition-colors duration-200 last:border-b-0 hover:bg-[#FFF8EC] sm:h-[66px] sm:px-7">
      <div className="min-w-0">
        <div className="flex min-w-0 items-center gap-2">
          <h2 className="truncate text-[15px] font-bold leading-tight tracking-tight text-black sm:text-base">{job.title}</h2>
        </div>
        <p className="mt-1 truncate text-xs font-medium leading-4 text-[#6B6B6B] sm:text-sm">
          {job.description}
        </p>
      </div>

      <div className="flex min-w-0 items-center gap-2 justify-end">
        <div className="flex min-w-0 flex-nowrap items-center gap-2">
          <Badge tone={locationTone(job.location)} icon="location" className="max-w-[116px] truncate sm:max-w-[220px]">
            {job.location}
          </Badge>
        </div>

        <a
          href={job.applicationUrl}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`Apply for ${job.title}`}
          className="ml-auto inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-[#E8CFA8] bg-[#FFFEFB] text-[#171717] transition-all duration-200 hover:-translate-y-0.5 hover:bg-[#171717] hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#171717] sm:h-10 sm:w-10"
        >
          <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" aria-hidden="true" />
        </a>
      </div>
    </article>
  );
}
