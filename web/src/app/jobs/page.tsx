import { Suspense } from "react";
import JobFeedClient from "./JobFeedClient";

export default function JobFeedPage({
    searchParams,
}: {
    searchParams?: { search?: string; mode?: string };
}) {
    return (
        <Suspense fallback={<div className="min-h-screen" />}>
            <JobFeedClient
                initialSearch={searchParams?.search || ""}
                initialSortMode={searchParams?.mode === "relevance" ? "relevance" : "recency"}
            />
        </Suspense>
    );
}
