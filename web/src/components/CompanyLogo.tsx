// Company logo — shows colored initial circle (like the mood board reference)
// Uses deterministic color from company name hash

const LOGO_COLORS = [
    "#F0883E", "#58A6FF", "#3FB950", "#D29922", "#BC8CFF",
    "#FF7B72", "#79C0FF", "#FFA657", "#7EE787", "#D2A8FF",
];

function getColor(name: string): string {
    let hash = 0;
    for (let i = 0; i < name.length; i++) {
        hash = name.charCodeAt(i) + ((hash << 5) - hash);
    }
    return LOGO_COLORS[Math.abs(hash) % LOGO_COLORS.length];
}

interface CompanyLogoProps {
    company: string;
    size?: "sm" | "md" | "lg";
}

export default function CompanyLogo({ company, size = "md" }: CompanyLogoProps) {
    const color = getColor(company);
    const initial = company.charAt(0).toUpperCase();

    const sizes = {
        sm: "w-8 h-8 text-xs",
        md: "w-10 h-10 text-sm",
        lg: "w-14 h-14 text-lg",
    };

    return (
        <div
            className={`${sizes[size]} rounded-full flex items-center justify-center font-bold text-white shrink-0`}
            style={{ backgroundColor: color }}
        >
            {initial}
        </div>
    );
}
