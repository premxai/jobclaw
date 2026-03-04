"use client";
import { useState, useEffect } from "react";
import TopNav from "@/components/TopNav";
import { fetchStats } from "@/lib/api";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line, Sankey, Layer, Rectangle } from "recharts";
import { Activity, Building2, Layers, TrendingUp } from "lucide-react";

// Chart colors
const COLORS = ["#F0883E", "#58A6FF", "#3FB950", "#D29922", "#BC8CFF", "#FF7B72", "#79C0FF", "#FFA657"];

const CHART_TOOLTIP_STYLE = {
    contentStyle: {
        backgroundColor: "#161B22",
        border: "1px solid #30363D",
        borderRadius: "8px",
        color: "#E6EDF3",
        fontSize: "13px",
    },
    cursor: { fill: "rgba(240, 136, 62, 0.08)" },
};

export default function DashboardPage() {
    const [stats, setStats] = useState<any>(null);

    useEffect(() => {
        fetchStats().then(setStats);
    }, []);

    if (!stats) {
        return (
            <div className="min-h-screen">
                <TopNav />
                <div className="max-w-7xl mx-auto px-6 py-8">
                    <div className="grid grid-cols-4 gap-5 mb-8">
                        {[1, 2, 3, 4].map((i) => (
                            <div key={i} className="stat-card h-24 animate-pulse" />
                        ))}
                    </div>
                </div>
            </div>
        );
    }

    // Transform data for charts
    const categoryData = Object.entries(stats.categories || {}).map(([name, value]) => ({
        name,
        value: Number(value),
    }));

    const sourceData = Object.entries(stats.by_source || {})
        .map(([name, value]) => ({ name: formatSourceName(name), value: Number(value) }))
        .sort((a, b) => b.value - a.value)
        .slice(0, 8);

    // Sankey data: Source → Category flow
    const sankeyNodes = [
        ...new Set([...sourceData.map((s) => s.name), ...categoryData.map((c) => c.name)]),
    ].map((name) => ({ name }));

    const sankeyLinks = sourceData.flatMap((source) =>
        categoryData.map((cat) => ({
            source: sankeyNodes.findIndex((n) => n.name === source.name),
            target: sankeyNodes.findIndex((n) => n.name === cat.name),
            value: Math.max(1, Math.round((source.value * cat.value) / stats.total_jobs)),
        }))
    ).filter((l) => l.value > 1 && l.source !== -1 && l.target !== -1);

    // Simulated daily trend data
    const trendData = Array.from({ length: 14 }, (_, i) => {
        const d = new Date();
        d.setDate(d.getDate() - (13 - i));
        return {
            date: d.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
            jobs: Math.floor(20 + Math.random() * 40 + i * 3),
        };
    });

    const statCards = [
        { icon: Activity, label: "Total Jobs", value: stats.total_jobs.toLocaleString(), color: "#F0883E" },
        { icon: Building2, label: "Companies", value: stats.total_companies.toLocaleString(), color: "#58A6FF" },
        { icon: Layers, label: "Sources", value: String(stats.sources), color: "#3FB950" },
        { icon: TrendingUp, label: "Categories", value: String(Object.keys(stats.categories || {}).length), color: "#D29922" },
    ];

    return (
        <div className="min-h-screen">
            <TopNav />

            <div className="max-w-7xl mx-auto px-6 py-8">
                <h1 className="text-3xl font-bold tracking-tight mb-8">Dashboard</h1>

                {/* Stat cards */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-5 mb-8">
                    {statCards.map((stat, i) => (
                        <div key={i} className="stat-card animate-slide-up" style={{ animationDelay: `${i * 50}ms` }}>
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ backgroundColor: stat.color + "15" }}>
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

                {/* Charts grid */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-8">
                    {/* Jobs by Category — Pie */}
                    <div className="stat-card">
                        <h2 className="font-semibold text-sm mb-4">Jobs by Category</h2>
                        <ResponsiveContainer width="100%" height={280}>
                            <PieChart>
                                <Pie
                                    data={categoryData}
                                    cx="50%"
                                    cy="50%"
                                    innerRadius={60}
                                    outerRadius={100}
                                    paddingAngle={3}
                                    dataKey="value"
                                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                                    labelLine={false}
                                >
                                    {categoryData.map((_, i) => (
                                        <Cell key={i} fill={COLORS[i % COLORS.length]} />
                                    ))}
                                </Pie>
                                <Tooltip {...CHART_TOOLTIP_STYLE} />
                            </PieChart>
                        </ResponsiveContainer>
                    </div>

                    {/* Top Sources — Bar */}
                    <div className="stat-card">
                        <h2 className="font-semibold text-sm mb-4">Top Sources</h2>
                        <ResponsiveContainer width="100%" height={280}>
                            <BarChart data={sourceData} layout="vertical" margin={{ left: 10 }}>
                                <XAxis type="number" stroke="#8B949E" fontSize={11} />
                                <YAxis type="category" dataKey="name" stroke="#8B949E" fontSize={11} width={90} />
                                <Tooltip {...CHART_TOOLTIP_STYLE} />
                                <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                                    {sourceData.map((_, i) => (
                                        <Cell key={i} fill={COLORS[i % COLORS.length]} />
                                    ))}
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* Trend — Line chart (full width) */}
                <div className="stat-card mb-8">
                    <h2 className="font-semibold text-sm mb-4">Jobs Discovered Over Time</h2>
                    <ResponsiveContainer width="100%" height={250}>
                        <LineChart data={trendData}>
                            <XAxis dataKey="date" stroke="#8B949E" fontSize={11} />
                            <YAxis stroke="#8B949E" fontSize={11} />
                            <Tooltip {...CHART_TOOLTIP_STYLE} />
                            <Line
                                type="monotone"
                                dataKey="jobs"
                                stroke="#F0883E"
                                strokeWidth={2.5}
                                dot={{ fill: "#F0883E", r: 3 }}
                                activeDot={{ r: 5 }}
                            />
                        </LineChart>
                    </ResponsiveContainer>
                </div>

                {/* Sankey — Source to Category Flow */}
                {sankeyLinks.length > 0 && (
                    <div className="stat-card">
                        <h2 className="font-semibold text-sm mb-4">Source → Category Flow</h2>
                        <p className="text-xs text-text-secondary mb-4">How jobs flow from sources into categories</p>
                        <ResponsiveContainer width="100%" height={350}>
                            <Sankey
                                data={{ nodes: sankeyNodes, links: sankeyLinks }}
                                nodeWidth={12}
                                nodePadding={24}
                                margin={{ left: 0, right: 150, top: 10, bottom: 10 }}
                                link={{ stroke: "#30363D", strokeOpacity: 0.5 }}
                            >
                                <Tooltip {...CHART_TOOLTIP_STYLE} />
                            </Sankey>
                        </ResponsiveContainer>
                    </div>
                )}
            </div>
        </div>
    );
}

function formatSourceName(ats: string): string {
    const map: Record<string, string> = {
        greenhouse: "Greenhouse",
        lever: "Lever",
        workday: "Workday",
        "github-swe-newgrad": "GitHub SWE",
        "github-ai-newgrad": "GitHub AI",
        "github-internship": "GitHub Intern",
        "github-new-grad": "GitHub Grad",
        indeed: "Indeed",
        linkedin: "LinkedIn",
        brave_search: "Brave",
    };
    return map[ats] || ats;
}
