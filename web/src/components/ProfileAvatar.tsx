import type { CSSProperties } from "react";

type ProfileAvatarProps = {
    name?: string | null;
    size?: "sm" | "lg";
};

const palettes = [
    { paper: "#F3E4C7", ink: "#355227", leaf: "#78935A" },
    { paper: "#E5EEDC", ink: "#214B36", leaf: "#9AAE73" },
    { paper: "#F0DDD1", ink: "#633E31", leaf: "#B8805E" },
    { paper: "#E8E1F0", ink: "#44395E", leaf: "#9A8AB9" },
];

function initialsFor(name: string) {
    const initials = name
        .trim()
        .split(/\s+/)
        .filter(Boolean)
        .map((part) => part[0])
        .join("")
        .slice(0, 2)
        .toUpperCase();
    return initials || "NN";
}

function paletteFor(name: string) {
    const hash = name.split("").reduce((sum, character) => sum + character.charCodeAt(0), 0);
    return palettes[hash % palettes.length];
}

export default function ProfileAvatar({ name = "Nori Note", size = "sm" }: ProfileAvatarProps) {
    const label = (name || "").trim() || "Nori Note";
    const palette = paletteFor(label);
    const initials = initialsFor(label);
    const sizeClass = size === "lg" ? "h-[112px] w-[112px] xl:h-[124px] xl:w-[124px]" : "h-12 w-12";
    const textSize = size === "lg" ? 28 : 12;
    const style = { "--avatar-paper": palette.paper, "--avatar-ink": palette.ink, "--avatar-leaf": palette.leaf } as CSSProperties;

    return (
        <span
            className={`relative grid shrink-0 place-items-center overflow-hidden rounded-full border border-white/75 bg-[var(--avatar-paper)] shadow-[inset_0_0_0_5px_rgba(255,255,255,0.62),0_10px_24px_rgba(47,74,29,0.14)] ${sizeClass}`}
            style={style}
            role="img"
            aria-label={`${label} profile avatar`}
        >
            <svg viewBox="0 0 112 112" className="absolute inset-0 h-full w-full" aria-hidden="true">
                <circle cx="56" cy="56" r="43" fill="none" stroke="var(--avatar-ink)" strokeOpacity=".18" strokeWidth="1.5" />
                <circle cx="56" cy="56" r="35" fill="none" stroke="var(--avatar-ink)" strokeOpacity=".1" strokeDasharray="2 5" strokeWidth="1.5" />
                <path d="M19 73c9-4 17-11 21-21 3 10 1 21-8 27-4 3-9 3-13 1Z" fill="var(--avatar-leaf)" opacity=".82" />
                <path d="M22 74c6-5 11-11 15-19" fill="none" stroke="var(--avatar-ink)" strokeLinecap="round" strokeWidth="2" opacity=".58" />
                <path d="M86 28l2.5 5.5L94 36l-5.5 2.5L86 44l-2.5-5.5L78 36l5.5-2.5Z" fill="var(--avatar-leaf)" opacity=".9" />
                <path d="M81 84c4-5 9-8 15-8-2 7-7 11-15 12Z" fill="var(--avatar-leaf)" opacity=".54" />
                <text x="56" y="64" fill="var(--avatar-ink)" fontFamily="Georgia, serif" fontSize={textSize} fontWeight="700" letterSpacing="-1.5" textAnchor="middle">
                    {initials}
                </text>
            </svg>
        </span>
    );
}
