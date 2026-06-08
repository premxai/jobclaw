"use client";

import { cn } from "@/lib/utils";
import type { BoardCategory, BoardJob } from "@/lib/job-board";
import { BOARD_CATEGORIES } from "@/lib/job-board";

interface CategoryTabsProps {
  jobs: BoardJob[];
  activeCategory: BoardCategory;
  onChange: (category: BoardCategory) => void;
}

function countForCategory(jobs: BoardJob[], category: BoardCategory): number {
  if (category === "All Roles") return jobs.length;
  return jobs.filter((job) => job.category === category).length;
}

export default function CategoryTabs({ jobs, activeCategory, onChange }: CategoryTabsProps) {
  return (
    <div className="mx-auto flex w-fit max-w-full flex-wrap justify-center gap-2 rounded-2xl border border-white/45 bg-white/38 p-1.5 shadow-[0_12px_40px_rgba(41,29,12,0.12)] backdrop-blur-2xl">
      {BOARD_CATEGORIES.map((category) => {
        const isActive = activeCategory === category;
        const count = countForCategory(jobs, category);

        return (
          <button
            key={category}
            type="button"
            onClick={() => onChange(category)}
            className={cn(
              "group inline-flex h-9 shrink-0 items-center gap-2 rounded-full border px-3.5 text-sm font-semibold transition-all duration-200 backdrop-blur-2xl sm:h-10 sm:px-4",
              isActive
                ? "border-black/80 bg-black/88 text-white shadow-[0_8px_20px_rgba(0,0,0,0.14)]"
                : "border-white/45 bg-white/42 text-zinc-700 shadow-sm hover:bg-white/60 hover:text-zinc-950",
            )}
            aria-pressed={isActive}
          >
            <span>{category}</span>
            <span
              className={cn(
                "inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[11px] font-bold",
                isActive ? "bg-white/15 text-white" : "bg-white/55 text-zinc-500 group-hover:bg-white/75",
              )}
            >
              {count}
            </span>
          </button>
        );
      })}
    </div>
  );
}
