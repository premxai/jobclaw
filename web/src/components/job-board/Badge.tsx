import { MapPin } from "lucide-react";

import { cn } from "@/lib/utils";

interface BadgeProps {
  children: React.ReactNode;
  tone?: "neutral" | "remote" | "hybrid";
  icon?: "location";
  className?: string;
}

export default function Badge({ children, tone = "neutral", icon, className }: BadgeProps) {
  const Icon = icon === "location" ? MapPin : null;

  return (
    <span
      className={cn(
        "inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full border px-3 text-xs font-semibold leading-none",
        tone === "neutral" && "border-[#E8CFA8] bg-[#FFFEFB] text-[#333333]",
        tone === "remote" && "border-[#c8e5bc] bg-[#f0f8e9]/88 text-[#2f7d4a]",
        tone === "hybrid" && "border-[#bfd6ff] bg-[#eef5ff]/88 text-[#3168d8]",
        className,
      )}
    >
      {Icon && <Icon className="h-3.5 w-3.5" aria-hidden="true" />}
      {children}
    </span>
  );
}
