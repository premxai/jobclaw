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
    <div className="mx-auto flex w-fit max-w-full flex-wrap justify-center gap-3 rounded-[22px] border border-[#e7cda9]/70 bg-[#fff5e6]/55 p-1.5 shadow-[0_10px_34px_rgba(86,55,22,0.13)] backdrop-blur-md">
      {BOARD_CATEGORIES.map((category) => {
        const isActive = activeCategory === category;
        const count = countForCategory(jobs, category);

        return (
          <button
            key={category}
            type="button"
            onClick={() => onChange(category)}
            className={cn(
              "group inline-flex h-9 shrink-0 items-center gap-2 rounded-[17px] border px-3.5 text-sm font-semibold transition-all duration-200 sm:h-10 sm:px-4",
              isActive
                ? "border-[#11100f] bg-[#1b1a18] text-[#fff8ee] shadow-[0_3px_0_rgba(0,0,0,0.32),0_10px_22px_rgba(41,27,12,0.16)]"
                : "border-[#e5c7a2] bg-[#fff8ed]/84 text-[#3e3a34] shadow-[0_2px_0_rgba(139,92,43,0.12)] hover:-translate-y-0.5 hover:border-[#d9b88f] hover:bg-[#fffaf3]",
            )}
            aria-pressed={isActive}
          >
            <span>{category}</span>
            <span
              className={cn(
                "inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[11px] font-bold",
                isActive ? "bg-[#fff8ee]/18 text-[#fff8ee]" : "bg-[#eadcc8] text-[#746a5e] group-hover:bg-[#e3d1ba]",
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
