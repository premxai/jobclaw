export type BoardCategory = "All Roles" | "Engineering" | "Design" | "Product" | "Growth" | "AI/ML" | "Internships";

export type LocationType = "Remote" | "Hybrid" | "On-site";
export type JobType = "Full-time" | "Internship" | "Contract";

export interface BoardJob {
  id: string;
  title: string;
  category: Exclude<BoardCategory, "All Roles">;
  description: string;
  locationType: LocationType;
  jobType: JobType;
  isHot: boolean;
  applicationUrl: string;
  postedAt: string;
  source: string;
  company?: string;
}

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
    description: "Build models that power intelligent product workflows.",
    locationType: "Remote",
    jobType: "Full-time",
    isHot: true,
    applicationUrl: "https://example.com/apply/machine-learning-engineer",
    postedAt: "2026-06-06",
    source: "Company Careers",
    company: "JobClaw Demo",
  },
  {
    id: "mock-ai-intern",
    title: "AI Engineer Intern",
    category: "Internships",
    description: "Evaluate AI systems for real-world product use cases.",
    locationType: "Remote",
    jobType: "Internship",
    isHot: true,
    applicationUrl: "https://example.com/apply/ai-engineer-intern",
    postedAt: "2026-06-06",
    source: "Company Careers",
    company: "JobClaw Demo",
  },
  {
    id: "mock-data-scientist",
    title: "Data Scientist",
    category: "AI/ML",
    description: "Surface actionable insights from product and marketplace data.",
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
    description: "Own core AI infrastructure from prototype to production.",
    locationType: "Hybrid",
    jobType: "Full-time",
    isHot: true,
    applicationUrl: "https://example.com/apply/founding-ai-engineer",
    postedAt: "2026-06-05",
    source: "Company Careers",
    company: "JobClaw Demo",
  },
  {
    id: "mock-product-designer",
    title: "Product Designer",
    category: "Design",
    description: "Design polished product flows from research to final UI.",
    locationType: "Remote",
    jobType: "Full-time",
    isHot: true,
    applicationUrl: "https://example.com/apply/product-designer",
    postedAt: "2026-06-04",
    source: "Company Careers",
    company: "JobClaw Demo",
  },
  {
    id: "mock-product-manager",
    title: "Product Manager",
    category: "Product",
    description: "Shape roadmap strategy and ship products people rely on.",
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
    description: "Run lifecycle experiments across acquisition and retention.",
    locationType: "Remote",
    jobType: "Contract",
    isHot: false,
    applicationUrl: "https://example.com/apply/growth-marketer",
    postedAt: "2026-06-02",
    source: "Company Careers",
    company: "JobClaw Demo",
  },
];

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

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

function cleanDescription(job: ApiJob): string {
  const raw = job.description?.replace(/\s+/g, " ").trim();
  if (raw && raw.length > 12) return raw.length > 112 ? `${raw.slice(0, 109).trim()}...` : raw;
  if (job.company) return `Join ${job.company} to build thoughtful products and systems.`;
  return "Build and ship meaningful work with a high-quality team.";
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
  return {
    id: job.internal_hash || job.job_id || `api-job-${index}`,
    title: job.title || "Untitled Role",
    category: classifyCategory(job),
    description: cleanDescription(job),
    locationType: classifyLocation(job.location),
    jobType: classifyJobType(job),
    isHot: isHotJob(job),
    applicationUrl: job.url || "#",
    postedAt: job.date_posted || job.first_seen || new Date().toISOString(),
    source: sourceLabel(job.source_ats),
    company: job.company,
  };
}

export async function fetchBoardJobs(): Promise<{ jobs: BoardJob[]; usingFallback: boolean }> {
  try {
    const response = await fetch(`${API_BASE}/jobs?per_page=100`, { cache: "no-store" });
    if (!response.ok) throw new Error(`Jobs API ${response.status}`);
    const data = (await response.json()) as JobsResponse;
    const jobs = (data.jobs || []).map(mapApiJobToBoardJob).filter((job) => job.applicationUrl !== "#");
    if (!jobs.length) throw new Error("Jobs API returned no jobs");
    return { jobs, usingFallback: false };
  } catch {
    return { jobs: MOCK_BOARD_JOBS, usingFallback: true };
  }
}

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
