import { Clock, Flame, MapPin } from "lucide-react";

import { cn } from "@/lib/utils";
import type { LocationType } from "@/lib/job-board";

interface BadgeProps {
  children: React.ReactNode;
  tone?: "neutral" | "remote" | "hybrid" | "hot";
  icon?: "location" | "clock" | "hot";
}

export default function Badge({ children, tone = "neutral", icon }: BadgeProps) {
  const Icon = icon === "location" ? MapPin : icon === "clock" ? Clock : icon === "hot" ? Flame : null;

  return (
    <span
      className={cn(
        "inline-flex h-6 shrink-0 items-center gap-1 rounded-full border px-2 text-[11px] font-semibold leading-none",
        tone === "neutral" && "border-zinc-200 bg-zinc-100 text-zinc-600",
        tone === "remote" && "border-emerald-200 bg-emerald-50 text-emerald-700",
        tone === "hybrid" && "border-blue-200 bg-blue-50 text-blue-700",
        tone === "hot" && "border-amber-200 bg-amber-50 text-orange-600",
      )}
    >
      {Icon && <Icon className="h-3 w-3" aria-hidden="true" />}
      {children}
    </span>
  );
}

export function locationTone(locationType: LocationType): "remote" | "hybrid" | "neutral" {
  if (locationType === "Remote") return "remote";
  if (locationType === "Hybrid") return "hybrid";
  return "neutral";
}
