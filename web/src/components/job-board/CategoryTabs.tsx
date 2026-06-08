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
    <div className="mx-auto flex w-fit max-w-full flex-wrap justify-center gap-3 sm:gap-5">
      {BOARD_CATEGORIES.map((category) => {
        const isActive = activeCategory === category;
        const count = countForCategory(jobs, category);

        return (
          <button
            key={category}
            type="button"
            onClick={() => onChange(category)}
            className={cn(
              "group inline-flex h-10 shrink-0 items-center gap-2.5 rounded-[18px] border px-4 text-sm font-semibold transition-all duration-200 sm:h-11 sm:px-5 sm:text-[15px]",
              isActive
                ? "border-[#171717] bg-[#171717] text-white shadow-[0_8px_20px_rgba(0,0,0,0.16)]"
                : "border-[#E8CFA8] bg-[#FFFDF7] text-[#333333] shadow-[0_1px_0_rgba(120,80,40,0.08)] hover:-translate-y-0.5 hover:bg-white",
            )}
            aria-pressed={isActive}
          >
            <span>{category}</span>
            <span
              className={cn(
                "inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[11px] font-bold",
                isActive ? "bg-white/15 text-white" : "bg-[#EFE5D6] text-[#6B6B6B]",
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
