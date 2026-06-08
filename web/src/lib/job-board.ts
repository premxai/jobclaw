export type BoardCategory = "All Roles" | "Engineering" | "Design" | "Product" | "Growth" | "AI/ML" | "Internships";

export type LocationType = "Remote" | "Hybrid" | "On-site";
export type JobType = "Full-time" | "Internship" | "Contract";

export interface BoardJob {
  id: string;
  title: string;
  category: Exclude<BoardCategory, "All Roles">;
  description: string;
  location: string;
  locationType: LocationType;
  jobType: JobType;
  isHot: boolean;
  applicationUrl: string;
  postedAt: string;
  source: string;
  company?: string;
}

export type BoardDataStatus = "real" | "empty" | "unavailable" | "mock";

interface ApiJob {
  internal_hash?: string;
  job_id?: string;
  title?: string;
  company?: string;
  location?: string;
  url?: string;
  date_posted?: string;
  first_seen?: string | null;
  source_ats?: string;
  keywords_matched?: string[] | string | null;
  description?: string | null;
}

interface JobsResponse {
  jobs?: ApiJob[];
  total?: number;
}

interface RunsResponseItem {
  run_at?: string;
  scraper?: string;
}

export const BOARD_CATEGORIES: BoardCategory[] = [
  "All Roles",
  "Engineering",
  "Design",
  "Product",
  "Growth",
  "AI/ML",
  "Internships",
];

export const MOCK_BOARD_JOBS: BoardJob[] = [
  {
    id: "mock-ml-engineer",
    title: "Machine Learning Engineer",
    category: "AI/ML",
    description: "Work on AI systems and product-grade model workflows at JobClaw Demo.",
    location: "Remote",
    locationType: "Remote",
    jobType: "Full-time",
    isHot: false,
    applicationUrl: "https://example.com/apply/machine-learning-engineer",
    postedAt: "2026-06-06",
    source: "Company Careers",
    company: "JobClaw Demo",
  },
  {
    id: "mock-ai-intern",
    title: "AI Engineer Intern",
    category: "Internships",
    description: "Early-career AI role focused on evaluation, tooling, and applied product use cases.",
    location: "Remote",
    locationType: "Remote",
    jobType: "Internship",
    isHot: false,
    applicationUrl: "https://example.com/apply/ai-engineer-intern",
    postedAt: "2026-06-06",
    source: "Company Careers",
    company: "JobClaw Demo",
  },
  {
    id: "mock-data-scientist",
    title: "Data Scientist",
    category: "AI/ML",
    description: "Use product and marketplace data to ship sharper insights for real teams.",
    location: "Remote",
    locationType: "Remote",
    jobType: "Full-time",
    isHot: false,
    applicationUrl: "https://example.com/apply/data-scientist",
    postedAt: "2026-06-05",
    source: "Company Careers",
    company: "JobClaw Demo",
  },
  {
    id: "mock-founding-ai-engineer",
    title: "Founding AI Engineer",
    category: "Engineering",
    description: "Own core AI infrastructure from prototype through reliable production systems.",
    location: "San Francisco, CA",
    locationType: "Hybrid",
    jobType: "Full-time",
    isHot: false,
    applicationUrl: "https://example.com/apply/founding-ai-engineer",
    postedAt: "2026-06-05",
    source: "Company Careers",
    company: "JobClaw Demo",
  },
  {
    id: "mock-product-designer",
    title: "Product Designer",
    category: "Design",
    description: "Shape product flows from user research through polished, shippable UI.",
    location: "Remote",
    locationType: "Remote",
    jobType: "Full-time",
    isHot: false,
    applicationUrl: "https://example.com/apply/product-designer",
    postedAt: "2026-06-04",
    source: "Company Careers",
    company: "JobClaw Demo",
  },
  {
    id: "mock-product-manager",
    title: "Product Manager",
    category: "Product",
    description: "Guide roadmap, customer insight, and execution for a focused product team.",
    location: "New York, NY",
    locationType: "Hybrid",
    jobType: "Full-time",
    isHot: false,
    applicationUrl: "https://example.com/apply/product-manager",
    postedAt: "2026-06-03",
    source: "Company Careers",
    company: "JobClaw Demo",
  },
  {
    id: "mock-growth-marketer",
    title: "Growth Marketer",
    category: "Growth",
    description: "Run acquisition, lifecycle, and retention experiments with measurable impact.",
    location: "Remote",
    locationType: "Remote",
    jobType: "Contract",
    isHot: false,
    applicationUrl: "https://example.com/apply/growth-marketer",
    postedAt: "2026-06-02",
    source: "Company Careers",
    company: "JobClaw Demo",
  },
];

const API_BASE = "/api";
const BOARD_FRESHNESS_HOURS = 48;
const BOARD_REFRESH_INTERVAL_MS = 15 * 60 * 1000;
const ENABLE_MOCK_JOBS = process.env.NEXT_PUBLIC_ENABLE_MOCK_JOBS === "1";

function keywordText(job: ApiJob): string {
  const keywords = job.keywords_matched;
  if (Array.isArray(keywords)) return keywords.join(" ");
  return keywords || "";
}

function classifyCategory(job: ApiJob): BoardJob["category"] {
  const text = `${job.title || ""} ${job.description || ""} ${keywordText(job)}`.toLowerCase();

  if (/\b(intern|internship|new grad|graduate)\b/.test(text)) return "Internships";
  if (/\b(ai|ml|machine learning|llm|research scientist|deep learning|data scientist)\b/.test(text)) return "AI/ML";
  if (/\b(design|designer|ux|ui|product design)\b/.test(text)) return "Design";
  if (/\b(product manager|product management|\bpm\b)\b/.test(text)) return "Product";
  if (/\b(growth|marketing|marketer|lifecycle|acquisition|retention)\b/.test(text)) return "Growth";

  return "Engineering";
}

function classifyLocation(location?: string): LocationType {
  const text = (location || "").toLowerCase();
  if (text.includes("remote")) return "Remote";
  if (text.includes("hybrid")) return "Hybrid";
  return "On-site";
}

function classifyJobType(job: ApiJob): JobType {
  const text = `${job.title || ""} ${job.description || ""}`.toLowerCase();
  if (/\b(intern|internship|new grad|graduate)\b/.test(text)) return "Internship";
  if (/\b(contract|contractor|freelance|temporary)\b/.test(text)) return "Contract";
  return "Full-time";
}

function cleanLocation(location?: string): string {
  const raw = location?.replace(/\s+/g, " ").trim();
  if (!raw) return "Location TBD";

  return raw.length > 42 ? `${raw.slice(0, 39).trim()}...` : raw;
}

function sourceLabel(source?: string): string {
  if (!source) return "Company Careers";
  const labels: Record<string, string> = {
    greenhouse: "Greenhouse",
    lever: "Lever",
    ashby: "Ashby",
    workday: "Workday",
    workable: "Workable",
    rippling: "Rippling",
    smartrecruiters: "SmartRecruiters",
    bamboohr: "BambooHR",
    rss: "RSS",
    linkedin: "LinkedIn",
    indeed: "Indeed",
  };
  return labels[source] || source.replace(/[-_]/g, " ");
}

function roleDescription(job: ApiJob, category: BoardJob["category"]): string {
  const company = job.company?.trim() || "the hiring team";

  if (category === "Internships") {
    return `Early-career role at ${company} focused on learning, shipping, and real product work.`;
  }

  if (category === "AI/ML") {
    return `Work on AI, data, and model-driven systems with ${company}.`;
  }

  if (category === "Design") {
    return `Shape user-facing product experiences at ${company} from research to polished UI.`;
  }

  if (category === "Product") {
    return `Guide roadmap, customer insight, and execution for ${company}.`;
  }

  if (category === "Growth") {
    return `Grow ${company} through acquisition, lifecycle, and retention experiments.`;
  }

  return `Build production software and reliable systems with ${company}.`;
}

function looksLikeNoisyDescription(raw: string): boolean {
  const text = raw.toLowerCase();
  return (
    text.startsWith("http") ||
    text.includes("click here") ||
    text.includes("apply now") ||
    text.includes("job search") ||
    text.includes("jobs hiring") ||
    text.includes("salary estimate")
  );
}

function cleanDescription(job: ApiJob, category: BoardJob["category"]): string {
  const raw = job.description?.replace(/\s+/g, " ").trim();
  if (raw && raw.length > 24 && !looksLikeNoisyDescription(raw)) {
    return raw.length > 118 ? `${raw.slice(0, 115).trim()}...` : raw;
  }

  return roleDescription(job, category);
}

function isHotJob(job: ApiJob): boolean {
  const dateValue = job.first_seen || job.date_posted;
  if (!dateValue) return false;
  const date = new Date(dateValue);
  if (Number.isNaN(date.getTime())) return false;
  const ageMs = Date.now() - date.getTime();
  return ageMs >= 0 && ageMs <= 1000 * 60 * 60 * 24 * 3;
}

export function mapApiJobToBoardJob(job: ApiJob, index: number): BoardJob {
  const category = classifyCategory(job);

  return {
    id: job.internal_hash || job.job_id || `api-job-${index}`,
    title: job.title || "Untitled Role",
    category,
    description: cleanDescription(job, category),
    location: cleanLocation(job.location),
    locationType: classifyLocation(job.location),
    jobType: classifyJobType(job),
    isHot: isHotJob(job),
    applicationUrl: job.url || "#",
    postedAt: job.date_posted || job.first_seen || new Date().toISOString(),
    source: sourceLabel(job.source_ats),
    company: job.company,
  };
}

async function fetchJobsWithParams(params: URLSearchParams): Promise<BoardJob[]> {
  const response = await fetch(`${API_BASE}/jobs?${params.toString()}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Jobs API ${response.status}`);
  const data = (await response.json()) as JobsResponse;
  return (data.jobs || []).map(mapApiJobToBoardJob).filter((job) => job.applicationUrl !== "#");
}

export async function fetchBoardJobs(): Promise<{ jobs: BoardJob[]; status: BoardDataStatus }> {
  const baseParams = {
    per_page: "200",
    recent_hours: String(BOARD_FRESHNESS_HOURS),
  };

  try {
    const acceptedParams = new URLSearchParams({
      ...baseParams,
      quality: "accepted",
    });
    const acceptedJobs = await fetchJobsWithParams(acceptedParams);
    if (acceptedJobs.length) return { jobs: acceptedJobs, status: "real" };

    // Real fresh jobs are better than fake jobs while quality labels catch up.
    const freshJobs = await fetchJobsWithParams(new URLSearchParams(baseParams));
    if (freshJobs.length) return { jobs: freshJobs, status: "real" };

    if (ENABLE_MOCK_JOBS) return { jobs: MOCK_BOARD_JOBS, status: "mock" };

    return { jobs: [], status: "empty" };
  } catch {
    if (ENABLE_MOCK_JOBS) return { jobs: MOCK_BOARD_JOBS, status: "mock" };

    return { jobs: [], status: "unavailable" };
  }
}

export { BOARD_FRESHNESS_HOURS, BOARD_REFRESH_INTERVAL_MS };

export async function fetchLastRefresh(): Promise<string> {
  try {
    const response = await fetch(`${API_BASE}/stats/runs?limit=1`, { cache: "no-store" });
    if (!response.ok) throw new Error(`Runs API ${response.status}`);
    const runs = (await response.json()) as RunsResponseItem[];
    return runs[0]?.run_at || new Date().toISOString();
  } catch {
    return new Date().toISOString();
  }
}
