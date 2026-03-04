"use client";
import { useState, useEffect, useMemo } from "react";
import TopNav from "@/components/TopNav";
import CompanyLogo from "@/components/CompanyLogo";
import {
    BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
    PieChart, Pie, Cell, LineChart, Line, Sankey,
} from "recharts";
import { Activity, Send, Target, Trophy, TrendingUp, Briefcase } from "lucide-react";

// Vibrant Sankey link colors
const SANKEY_COLORS = [
    "#F0883E", "#58A6FF", "#3FB950", "#D29922", "#BC8CFF",
    "#FF7B72", "#79C0FF", "#FFA657", "#7EE787", "#D2A8FF",
];

const PIE_COLORS = ["#F0883E", "#58A6FF", "#3FB950", "#D29922", "#BC8CFF", "#FF7B72", "#79C0FF", "#FFA657"];

const CHART_TOOLTIP_STYLE = {
    contentStyle: {
        backgroundColor: "#FFFFFF",
        border: "1px solid #E5DDD0",
        borderRadius: "8px",
        color: "#1A1A1A",
        fontSize: "13px",
        boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
    },
};

// Custom Sankey link with color
function CustomLink(props: any) {
    const { sourceX, targetX, sourceY, targetY, sourceControlX, targetControlX, linkWidth, index } = props;
    const color = SANKEY_COLORS[index % SANKEY_COLORS.length];
    return (
        <path
            d={`M${sourceX},${sourceY} C${sourceControlX},${sourceY} ${targetControlX},${targetY} ${targetX},${targetY}`}
            fill="none"
            stroke={color}
            strokeWidth={linkWidth}
            strokeOpacity={0.5}
        />
    );
}

// Custom Sankey node with color
function CustomNode(props: any) {
    const { x, y, width, height, index, payload } = props;
    const color = SANKEY_COLORS[index % SANKEY_COLORS.length];
    return (
        <g>
            <rect x={x} y={y} width={width} height={height} fill={color} rx={3} />
            <text
                x={x + width + 8}
                y={y + height / 2}
                textAnchor="start"
                dominantBaseline="central"
                fill="#1A1A1A"
                fontSize={12}
                fontWeight={500}
            >
                {payload?.name}
            </text>
        </g>
    );
}

interface TrackedJob {
    internal_hash: string;
    title: string;
    company: string;
    location: string;
    url: string;
    date_posted: string;
    source_ats: string;
    status: string;
    addedAt?: string;
    keywords_matched?: string;
    salary_min?: number | null;
    salary_max?: number | null;
}

export default function DashboardPage() {
    const [jobs, setJobs] = useState<TrackedJob[]>([]);

    useEffect(() => {
        const saved = localStorage.getItem("jobclaw_saved");
        if (saved) {
            try { setJobs(JSON.parse(saved)); } catch { }
        }
    }, []);

    // Derived stats
    const stats = useMemo(() => {
        const saved = jobs.filter((j) => j.status === "saved").length;
        const applied = jobs.filter((j) => j.status === "applied").length;
        const interview = jobs.filter((j) => j.status === "interview").length;
        const offer = jobs.filter((j) => j.status === "offer").length;
        const total = jobs.length;
        const responseRate = total > 0 ? Math.round(((interview + offer) / Math.max(applied, 1)) * 100) : 0;
        return { saved, applied, interview, offer, total, responseRate };
    }, [jobs]);

    // By category
    const categoryData = useMemo(() => {
        const map: Record<string, number> = {};
        jobs.forEach((j) => {
            let cat = "Other";
            try {
                const kw = JSON.parse(j.keywords_matched || "[]");
                if (kw.length > 0) cat = kw[0];
            } catch { }
            map[cat] = (map[cat] || 0) + 1;
        });
        return Object.entries(map).map(([name, value]) => ({ name, value }));
    }, [jobs]);

    // By company (top 8)
    const companyData = useMemo(() => {
        const map: Record<string, number> = {};
        jobs.forEach((j) => { map[j.company] = (map[j.company] || 0) + 1; });
        return Object.entries(map)
            .map(([name, value]) => ({ name, value }))
            .sort((a, b) => b.value - a.value)
            .slice(0, 8);
    }, [jobs]);

    // Application timeline (by week added)
    const timelineData = useMemo(() => {
        const dayMap: Record<string, number> = {};
        jobs.forEach((j) => {
            const d = j.addedAt || j.date_posted || new Date().toISOString();
            const day = new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric" });
            dayMap[day] = (dayMap[day] || 0) + 1;
        });
        return Object.entries(dayMap).map(([date, count]) => ({ date, applications: count }));
    }, [jobs]);

    // Sankey: Status → Category flow
    const sankeyData = useMemo(() => {
        if (jobs.length === 0) return null;

        const statuses = ["Saved", "Applied", "Interview", "Offer"];
        const categories = [...new Set(categoryData.map((c) => c.name))];
        const nodes = [...statuses, ...categories].map((name) => ({ name }));

        const linkMap: Record<string, number> = {};
        jobs.forEach((j) => {
            const statusLabel = j.status.charAt(0).toUpperCase() + j.status.slice(1);
            let cat = "Other";
            try {
                const kw = JSON.parse(j.keywords_matched || "[]");
                if (kw.length > 0) cat = kw[0];
            } catch { }
            const key = `${statusLabel}→${cat}`;
            linkMap[key] = (linkMap[key] || 0) + 1;
        });

        const links = Object.entries(linkMap)
            .map(([key, value]) => {
                const [src, tgt] = key.split("→");
                return {
                    source: nodes.findIndex((n) => n.name === src),
                    target: nodes.findIndex((n) => n.name === tgt),
                    value,
                };
            })
            .filter((l) => l.source !== -1 && l.target !== -1 && l.value > 0);

        if (links.length === 0) return null;
        return { nodes, links };
    }, [jobs, categoryData]);

    const statCards = [
        { icon: Briefcase, label: "Total Tracked", value: stats.total, color: "#E8713A" },
        { icon: Send, label: "Applied", value: stats.applied, color: "#3574D4" },
        { icon: Target, label: "Interviews", value: stats.interview, color: "#C98A1A" },
        { icon: Trophy, label: "Offers", value: stats.offer, color: "#2D8A4E" },
    ];

    // Pipeline funnel
    const funnelData = [
        { stage: "Saved", count: stats.saved, color: "#7A7062" },
        { stage: "Applied", count: stats.applied, color: "#3574D4" },
        { stage: "Interview", count: stats.interview, color: "#C98A1A" },
        { stage: "Offer", count: stats.offer, color: "#2D8A4E" },
    ];

    return (
        <div className="min-h-screen">
            <TopNav />

            <div className="max-w-7xl mx-auto px-6 py-8">
                <div className="mb-8">
                    <h1 className="text-3xl font-bold tracking-tight mb-1">My Dashboard</h1>
                    <p className="text-text-secondary text-sm">
                        Your job application insights and pipeline overview
                    </p>
                </div>

                {/* Stat cards */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-5 mb-8">
                    {statCards.map((stat, i) => (
                        <div key={i} className="stat-card animate-slide-up" style={{ animationDelay: `${i * 50}ms` }}>
                            <div className="flex items-center gap-3">
                                <div
                                    className="w-10 h-10 rounded-lg flex items-center justify-center"
                                    style={{ backgroundColor: stat.color + "15" }}
                                >
                                    <stat.icon className="w-5 h-5" style={{ color: stat.color }} />
                                </div>
                                <div>
                                    <p className="text-2xl font-bold" style={{ color: stat.color }}>{stat.value}</p>
                                    <p className="text-xs text-text-secondary">{stat.label}</p>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>

                {jobs.length === 0 ? (
                    // Empty state
                    <div className="text-center py-20 animate-fade-in">
                        <p className="text-6xl mb-4">📊</p>
                        <h2 className="text-xl font-bold text-text-primary mb-2">No application data yet</h2>
                        <p className="text-text-secondary mb-6">
                            Save jobs from the feed and move them through your tracker to see insights here.
                        </p>
                        <a href="/jobs" className="btn-primary">Browse Jobs</a>
                    </div>
                ) : (
                    <>
                        {/* Pipeline funnel */}
                        <div className="stat-card mb-8 animate-fade-in">
                            <h2 className="font-semibold text-sm mb-5">Application Pipeline</h2>
                            <div className="flex items-end gap-3 h-40">
                                {funnelData.map((stage, i) => {
                                    const maxCount = Math.max(...funnelData.map((s) => s.count), 1);
                                    const height = Math.max((stage.count / maxCount) * 100, 8);
                                    return (
                                        <div key={i} className="flex-1 flex flex-col items-center gap-2">
                                            <span className="text-lg font-bold" style={{ color: stage.color }}>
                                                {stage.count}
                                            </span>
                                            <div
                                                className="w-full rounded-t-lg transition-all duration-500"
                                                style={{
                                                    height: `${height}%`,
                                                    backgroundColor: stage.color,
                                                    opacity: 0.8,
                                                }}
                                            />
                                            <span className="text-xs text-text-secondary">{stage.stage}</span>
                                        </div>
                                    );
                                })}
                            </div>
                            {stats.applied > 0 && (
                                <div className="mt-4 pt-4 border-t border-border text-center">
                                    <p className="text-sm text-text-secondary">
                                        Response rate:{" "}
                                        <span className="font-bold text-accent">{stats.responseRate}%</span>
                                    </p>
                                </div>
                            )}
                        </div>

                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-8">
                            {/* Jobs by Category — Pie */}
                            {categoryData.length > 0 && (
                                <div className="stat-card">
                                    <h2 className="font-semibold text-sm mb-4">Applications by Category</h2>
                                    <ResponsiveContainer width="100%" height={260}>
                                        <PieChart>
                                            <Pie
                                                data={categoryData}
                                                cx="50%"
                                                cy="50%"
                                                innerRadius={55}
                                                outerRadius={95}
                                                paddingAngle={3}
                                                dataKey="value"
                                                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                                                labelLine={false}
                                            >
                                                {categoryData.map((_, i) => (
                                                    <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                                                ))}
                                            </Pie>
                                            <Tooltip {...CHART_TOOLTIP_STYLE} />
                                        </PieChart>
                                    </ResponsiveContainer>
                                </div>
                            )}

                            {/* Top Companies — Bar */}
                            {companyData.length > 0 && (
                                <div className="stat-card">
                                    <h2 className="font-semibold text-sm mb-4">Top Companies Applied</h2>
                                    <ResponsiveContainer width="100%" height={260}>
                                        <BarChart data={companyData} layout="vertical" margin={{ left: 10 }}>
                                            <XAxis type="number" stroke="#B8AFA0" fontSize={11} />
                                            <YAxis type="category" dataKey="name" stroke="#B8AFA0" fontSize={11} width={85} />
                                            <Tooltip {...CHART_TOOLTIP_STYLE} />
                                            <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                                                {companyData.map((_, i) => (
                                                    <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                                                ))}
                                            </Bar>
                                        </BarChart>
                                    </ResponsiveContainer>
                                </div>
                            )}
                        </div>

                        {/* Application Timeline */}
                        {timelineData.length > 1 && (
                            <div className="stat-card mb-8">
                                <h2 className="font-semibold text-sm mb-4">Application Timeline</h2>
                                <ResponsiveContainer width="100%" height={220}>
                                    <LineChart data={timelineData}>
                                        <XAxis dataKey="date" stroke="#B8AFA0" fontSize={11} />
                                        <YAxis stroke="#B8AFA0" fontSize={11} />
                                        <Tooltip {...CHART_TOOLTIP_STYLE} />
                                        <Line
                                            type="monotone"
                                            dataKey="applications"
                                            stroke="#E8713A"
                                            strokeWidth={2.5}
                                            dot={{ fill: "#E8713A", r: 3 }}
                                            activeDot={{ r: 5 }}
                                        />
                                    </LineChart>
                                </ResponsiveContainer>
                            </div>
                        )}

                        {/* Colorful Sankey — Status → Category Flow */}
                        {sankeyData && (
                            <div className="stat-card">
                                <h2 className="font-semibold text-sm mb-2">Application Flow</h2>
                                <p className="text-xs text-text-secondary mb-4">Pipeline stage → Job category</p>
                                <ResponsiveContainer width="100%" height={320}>
                                    <Sankey
                                        data={sankeyData}
                                        nodeWidth={14}
                                        nodePadding={28}
                                        margin={{ left: 0, right: 160, top: 10, bottom: 10 }}
                                        link={<CustomLink />}
                                        node={<CustomNode />}
                                    >
                                        <Tooltip {...CHART_TOOLTIP_STYLE} />
                                    </Sankey>
                                </ResponsiveContainer>
                            </div>
                        )}

                        {/* Recent activity */}
                        <div className="stat-card mt-8">
                            <h2 className="font-semibold text-sm mb-4">Recent Activity</h2>
                            <div className="space-y-3">
                                {jobs.slice(0, 5).map((job) => (
                                    <div key={job.internal_hash} className="flex items-center gap-3 py-2 border-b border-border last:border-0">
                                        <CompanyLogo company={job.company} size="sm" />
                                        <div className="flex-1 min-w-0">
                                            <p className="text-sm font-medium text-text-primary truncate">{job.title}</p>
                                            <p className="text-xs text-text-secondary">{job.company}</p>
                                        </div>
                                        <span className={`pill text-xs ${job.status === "offer" ? "bg-green-100 text-green-700" :
                                            job.status === "interview" ? "bg-yellow-100 text-yellow-700" :
                                                job.status === "applied" ? "bg-blue-100 text-blue-700" :
                                                    "pill-dark"
                                            }`}>
                                            {job.status.charAt(0).toUpperCase() + job.status.slice(1)}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}
