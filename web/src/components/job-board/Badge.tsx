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
        "inline-flex h-6 shrink-0 items-center gap-1 rounded-full border px-2 text-[11px] font-semibold leading-none",
        tone === "neutral" && "border-[#ded0bd] bg-[#fff8ed]/80 text-[#4f473d]",
        tone === "remote" && "border-[#c8e5bc] bg-[#f0f8e9]/88 text-[#2f7d4a]",
        tone === "hybrid" && "border-[#bfd6ff] bg-[#eef5ff]/88 text-[#3168d8]",
        className,
      )}
    >
      {Icon && <Icon className="h-3 w-3" aria-hidden="true" />}
      {children}
    </span>
  );
}
