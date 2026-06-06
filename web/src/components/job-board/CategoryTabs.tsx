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
    <div className="flex flex-wrap justify-center gap-2">
      {BOARD_CATEGORIES.map((category) => {
        const isActive = activeCategory === category;
        const count = countForCategory(jobs, category);

        return (
          <button
            key={category}
            type="button"
            onClick={() => onChange(category)}
            className={cn(
              "group inline-flex h-9 shrink-0 items-center gap-2 rounded-full px-3.5 text-sm font-semibold transition-all duration-200 sm:h-10 sm:px-4",
              isActive
                ? "bg-black text-white shadow-[0_8px_20px_rgba(0,0,0,0.14)]"
                : "bg-white/70 text-zinc-600 shadow-sm ring-1 ring-black/5 backdrop-blur hover:bg-white hover:text-zinc-900",
            )}
            aria-pressed={isActive}
          >
            <span>{category}</span>
            <span
              className={cn(
                "inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[11px] font-bold",
                isActive ? "bg-white/15 text-white" : "bg-zinc-200/80 text-zinc-500 group-hover:bg-zinc-300",
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
