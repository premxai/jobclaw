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
    <article className="group grid min-h-[clamp(34px,4.7dvh,42px)] grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-[#ead7bd]/85 px-4 py-[clamp(0.25rem,0.55dvh,0.375rem)] transition-colors duration-200 last:border-b-0 hover:bg-[#fff1dc]/58 sm:px-5">
      <div className="min-w-0">
        <div className="flex min-w-0 items-center gap-2">
          <h2 className="truncate text-sm font-semibold tracking-tight text-[#1e1c19] sm:text-[15px]">{job.title}</h2>
        </div>
        <p className="mt-0.5 truncate text-[11px] font-medium leading-4 text-[#71695e] sm:text-xs">
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
          className="ml-auto inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-[#e2c5a0] bg-[#fff8ed]/88 text-[#1e1c19] shadow-[0_2px_0_rgba(139,92,43,0.12)] transition-all duration-200 hover:-translate-y-0.5 hover:scale-105 hover:bg-[#1b1a18] hover:text-[#fff8ee] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1b1a18] sm:h-8 sm:w-8"
        >
          <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" aria-hidden="true" />
        </a>
      </div>
    </article>
  );
}
