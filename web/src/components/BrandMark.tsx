import Link from "next/link";
import { NotebookPen } from "lucide-react";

interface BrandMarkProps {
    href?: string;
    compact?: boolean;
    inverse?: boolean;
}

export default function BrandMark({ href = "/", compact = false, inverse = false }: BrandMarkProps) {
    const content = (
        <span className="inline-flex items-center gap-2.5">
            <span className={`grid h-10 w-10 place-items-center rounded-2xl shadow-soft ${inverse ? "bg-white text-ink" : "bg-ink text-white"}`}>
                <NotebookPen className="h-5 w-5" aria-hidden="true" />
            </span>
            {!compact && (
                <span className="leading-none">
                    <span className={`block text-base font-black tracking-tight ${inverse ? "text-white" : "text-ink"}`}>Nori Note</span>
                    <span className={`block text-[11px] font-semibold uppercase tracking-[0.18em] ${inverse ? "text-white/55" : "text-muted-ink"}`}>job notes</span>
                </span>
            )}
        </span>
    );

    return href ? (
        <Link href={href} className="group inline-flex items-center" aria-label="Nori Note home">
            {content}
        </Link>
    ) : (
        content
    );
}
