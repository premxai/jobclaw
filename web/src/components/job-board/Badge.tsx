import { Clock, MapPin } from "lucide-react";

import { cn } from "@/lib/utils";

interface BadgeProps {
  children: React.ReactNode;
  tone?: "neutral" | "remote" | "hybrid";
  icon?: "location" | "clock";
  className?: string;
}

export default function Badge({ children, tone = "neutral", icon, className }: BadgeProps) {
  const Icon = icon === "location" ? MapPin : icon === "clock" ? Clock : null;

  return (
    <span
      className={cn(
        "inline-flex h-6 shrink-0 items-center gap-1 rounded-full border px-2 text-[11px] font-semibold leading-none",
        tone === "neutral" && "border-zinc-200 bg-zinc-100 text-zinc-600",
        tone === "remote" && "border-emerald-200 bg-emerald-50 text-emerald-700",
        tone === "hybrid" && "border-blue-200 bg-blue-50 text-blue-700",
        className,
      )}
    >
      {Icon && <Icon className="h-3 w-3" aria-hidden="true" />}
      {children}
    </span>
  );
}
