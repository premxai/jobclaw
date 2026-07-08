"use client";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface StageChartProps {
    saved: number;
    applied: number;
    interview: number;
    offer: number;
}

// Mirrors STATUS_COLORS in dashboard/page.tsx (gray/blue/amber/green) so the
// chart reads as the same taxonomy as the stat cards and status pills above it,
// rather than introducing an unrelated palette.
const STAGE_COLORS: Record<string, string> = {
    Saved: "#080808",
    Applied: "#3C6FD7",
    Interview: "#B67A20",
    Offer: "#247A4D",
};

export default function StageChart({ saved, applied, interview, offer }: StageChartProps) {
    const data = [
        { stage: "Saved", count: saved },
        { stage: "Applied", count: applied },
        { stage: "Interview", count: interview },
        { stage: "Offer", count: offer },
    ];

    return (
        <div className="h-56 w-full">
            <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
                    <XAxis type="number" hide allowDecimals={false} />
                    <YAxis
                        type="category"
                        dataKey="stage"
                        width={72}
                        tickLine={false}
                        axisLine={false}
                        tick={{ fontSize: 12, fill: "#7A7062" }}
                    />
                    <Tooltip
                        cursor={{ fill: "rgba(8, 8, 8, 0.05)" }}
                        contentStyle={{ borderRadius: 12, border: "1px solid #E4E4E1", fontSize: 12 }}
                        formatter={(value?: number) => [value ?? 0, "Jobs"]}
                    />
                    <Bar dataKey="count" radius={[0, 6, 6, 0]} barSize={20}>
                        {data.map((entry) => (
                            <Cell key={entry.stage} fill={STAGE_COLORS[entry.stage]} />
                        ))}
                    </Bar>
                </BarChart>
            </ResponsiveContainer>
        </div>
    );
}
