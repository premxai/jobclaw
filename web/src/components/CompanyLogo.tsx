/* eslint-disable @next/next/no-img-element */
"use client";

import { useEffect, useMemo, useState } from "react";
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
    intel: "intel.com",
    linear: "linear.app",
    latitude: "latitude.com",
    meta: "meta.com",
    microsoft: "microsoft.com",
    netdocuments: "netdocuments.com",
    netflix: "netflix.com",
    notion: "notion.so",
    nvidia: "nvidia.com",
    openai: "openai.com",
    perplexity: "perplexity.ai",
    ramp: "ramp.com",
    reddit: "reddit.com",
    rippling: "rippling.com",
    stripe: "stripe.com",
    tesla: "tesla.com",
    tiktok: "tiktok.com",
    twilio: "twilio.com",
    uber: "uber.com",
    "applied-materials": "appliedmaterials.com",
    appian: "appian.com",
    boeing: "boeing.com",
    caci: "caci.com",
    clickup: "clickup.com",
    "cogent-security": "cogentsecurity.com",
    clear: "clearme.com",
    "rocket-companies": "rocketcompanies.com",
    "pnc-financial-services": "pnc.com",
    thumbtack: "thumbtack.com",
    "vertex-pharmaceuticals": "vrtx.com",
    verkada: "verkada.com",
    workable: "workable.com",
};

const FALLBACK_COLORS = ["#080808", "#3C6FD7", "#247A4D", "#B67A20", "#B4578F", "#C44E4E"];

const ATS_HOSTS = ["ashbyhq.com", "greenhouse.io", "lever.co", "workable.com", "smartrecruiters.com", "myworkdayjobs.com"];

function domainFromSourceUrl(sourceUrl?: string): string | null {
    if (!sourceUrl) return null;
    try {
        const parsed = new URL(sourceUrl);
        if (!/^https?:$/.test(parsed.protocol)) return null;
        const hostname = parsed.hostname.toLowerCase().replace(/^www\./, "");
        if (ATS_HOSTS.some((host) => hostname === host || hostname.endsWith(`.${host}`))) return null;
        const parts = hostname.split(".");
        return parts.length >= 2 ? parts.slice(-2).join(".") : null;
    } catch {
        return null;
    }
}

function logoUrls(company: string, sourceUrl?: string): string[] {
    const slug = companySlug(company);
    const domains = [domainFromSourceUrl(sourceUrl), KNOWN_DOMAINS[slug]].filter((domain, index, all): domain is string => Boolean(domain) && all.indexOf(domain) === index);
    return domains.flatMap((domain) => [
        `https://logo.clearbit.com/${domain}`,
        `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=128`,
        `https://icons.duckduckgo.com/ip3/${domain}.ico`,
    ]);
}

function fallbackColor(company: string): string {
    let hash = 0;
    for (let i = 0; i < company.length; i++) hash = company.charCodeAt(i) + ((hash << 5) - hash);
    return FALLBACK_COLORS[Math.abs(hash) % FALLBACK_COLORS.length];
}

interface CompanyLogoProps {
    company: string;
    sourceUrl?: string;
    size?: "sm" | "md" | "lg";
    shape?: "circle" | "rounded";
}

export default function CompanyLogo({ company, sourceUrl, size = "md", shape = "circle" }: CompanyLogoProps) {
    const [logoIndex, setLogoIndex] = useState(0);
    const logoSources = useMemo(() => logoUrls(company, sourceUrl), [company, sourceUrl]);
    const initial = initialsFor(company);

    useEffect(() => {
        setLogoIndex(0);
    }, [company, sourceUrl]);

    const sizes = {
        sm: "h-8 w-8 text-xs",
        md: "h-11 w-11 text-sm",
        lg: "h-16 w-16 text-lg",
    };
    const radius = shape === "rounded" ? "rounded-[10px]" : "rounded-full";

    return (
        <div className={`${sizes[size]} ${radius} grid shrink-0 place-items-center overflow-hidden border border-border bg-white shadow-card`}>
            {logoSources[logoIndex] ? (
                <img
                    src={logoSources[logoIndex]}
                    alt={`${company} logo`}
                    className="h-[72%] w-[72%] object-contain"
                    loading="lazy"
                    referrerPolicy="no-referrer"
                    onError={() => setLogoIndex((current) => current + 1)}
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
