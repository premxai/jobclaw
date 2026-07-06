// Home is the jobs feed itself (no separate "room scene" board) — see the
// redesign wireframe discussion: two near-duplicate job-list UIs was real
// maintenance overhead for little user value. HomeBrandStrip keeps a compact
// brand/trust moment; /jobs (JobFeedClient.tsx) remains reachable standalone
// without the strip for direct deep-links.
import JobFeedClient from "./jobs/JobFeedClient";
import HomeBrandStrip from "@/components/HomeBrandStrip";

export default function HomePage() {
  return <JobFeedClient initialSearch="" headerExtra={<HomeBrandStrip />} />;
}
