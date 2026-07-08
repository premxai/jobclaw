/* eslint-disable @next/next/no-img-element */
"use client";

import { useMemo, useState } from "react";
import { Building2 } from "lucide-react";
import { companySlug, initialsFor } from "@/lib/job-display";

const KNOWN_DOMAINS: Record<string, string> = {
    airbnb: "airbnb.com",
    amazon: "amazon.com",
    anthropic: "anthropic.com",
    apple: "apple.com",
    ashby: "ashbyhq.com",
    cursor: "cursor.com",
    databricks: "databricks.com",
    discord: "discord.com",
    doordash: "doordash.com",
    dribbble: "dribbble.com",
    figma: "figma.com",
    google: "google.com",
    greenhouse: "greenhouse.io",
    meta: "meta.com",
    microsoft: "microsoft.com",
    netflix: "netflix.com",
    nvidia: "nvidia.com",
    openai: "openai.com",
    ramp: "ramp.com",
    rippling: "rippling.com",
    stripe: "stripe.com",
    tesla: "tesla.com",
    tiktok: "tiktok.com",
    uber: "uber.com",
    workable: "workable.com",
};

const FALLBACK_COLORS = ["#080808", "#3C6FD7", "#247A4D", "#B67A20", "#B4578F", "#C44E4E"];

function knownLogoUrl(company: string): string | null {
    const slug = companySlug(company);
    const domain = KNOWN_DOMAINS[slug];
    if (!domain) return null;
    return `https://logo.clearbit.com/${domain}`;
}

function fallbackColor(company: string): string {
    let hash = 0;
    for (let i = 0; i < company.length; i++) hash = company.charCodeAt(i) + ((hash << 5) - hash);
    return FALLBACK_COLORS[Math.abs(hash) % FALLBACK_COLORS.length];
}

interface CompanyLogoProps {
    company: string;
    size?: "sm" | "md" | "lg";
    shape?: "circle" | "rounded";
}

export default function CompanyLogo({ company, size = "md", shape = "circle" }: CompanyLogoProps) {
    const [failed, setFailed] = useState(false);
    const logoUrl = useMemo(() => knownLogoUrl(company), [company]);
    const initial = initialsFor(company);

    const sizes = {
        sm: "h-8 w-8 text-xs",
        md: "h-11 w-11 text-sm",
        lg: "h-16 w-16 text-lg",
    };
    const radius = shape === "rounded" ? "rounded-[10px]" : "rounded-full";

    return (
        <div className={`${sizes[size]} ${radius} grid shrink-0 place-items-center overflow-hidden border border-border bg-white shadow-card`}>
            {logoUrl && !failed ? (
                <img
                    src={logoUrl}
                    alt={`${company} logo`}
                    className="h-[72%] w-[72%] object-contain"
                    loading="lazy"
                    onError={() => setFailed(true)}
                />
            ) : initial ? (
                <span
                    className={`grid h-full w-full place-items-center ${radius} text-sm font-black text-white`}
                    style={{ backgroundColor: fallbackColor(company) }}
                    aria-label={`${company} initials`}
                >
                    {initial}
                </span>
            ) : (
                <Building2 className="h-4 w-4 text-text-secondary" aria-hidden="true" />
            )}
        </div>
    );
}
