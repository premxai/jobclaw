import { ArrowRight } from "lucide-react";

import Badge, { locationTone } from "./Badge";
import type { BoardJob } from "@/lib/job-board";

interface JobRowProps {
  job: BoardJob;
}

export default function JobRow({ job }: JobRowProps) {
  return (
    <article className="group grid min-h-[48px] gap-2 border-b border-zinc-200/80 px-4 py-2 transition-colors duration-200 last:border-b-0 hover:bg-amber-50/45 sm:px-5 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center lg:gap-5">
      <div className="min-w-0">
        <div className="flex min-w-0 items-center gap-2">
          <h2 className="truncate text-sm font-semibold tracking-tight text-zinc-900 sm:text-[15px]">{job.title}</h2>
        </div>
        <p className="mt-0.5 line-clamp-1 max-w-2xl text-[11px] leading-4 text-zinc-500 sm:text-xs">
          {job.description}
        </p>
      </div>

      <div className="flex min-w-0 items-center gap-2 lg:justify-end">
        <div className="flex min-w-0 flex-nowrap items-center gap-2">
          <Badge tone={locationTone(job.locationType)} icon="location" className="max-w-[168px] truncate sm:max-w-[210px]">
            {job.location}
          </Badge>
          <Badge tone="neutral" icon="clock">
            {job.jobType}
          </Badge>
        </div>

        <a
          href={job.applicationUrl}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`Apply for ${job.title}`}
          className="ml-auto inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-zinc-100 text-zinc-500 transition-all duration-200 hover:scale-105 hover:bg-black hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black"
        >
          <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" aria-hidden="true" />
        </a>
      </div>
    </article>
  );
}
