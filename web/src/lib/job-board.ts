export type DiscordJobCategory =
  | "AI/ML"
  | "Data Science"
  | "Data Engineering"
  | "Data Analyst"
  | "SWE"
  | "New Grad"
  | "Product"
  | "Research"
  | "Uncategorized";

export type BoardCategory = "All Roles" | "AI/ML" | "SWE" | "Data" | "Other";
export type BoardJobCategory = Exclude<BoardCategory, "All Roles">;

export interface BoardJob {
  id: string;
  title: string;
  category: BoardJobCategory;
  description: string;
  location: string;
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
  has_more?: boolean;
}

interface RunsResponseItem {
  run_at?: string;
  scraper?: string;
}

export const BOARD_CATEGORIES: BoardCategory[] = [
  "All Roles",
  "AI/ML",
  "SWE",
  "Data",
  "Other",
];

const DISCORD_JOB_CATEGORIES = new Set<DiscordJobCategory>([
  "AI/ML",
  "Data Science",
  "Data Engineering",
  "Data Analyst",
  "SWE",
  "New Grad",
  "Product",
  "Research",
  "Uncategorized",
]);

export const MOCK_BOARD_JOBS: BoardJob[] = [
  {
    id: "mock-ml-engineer",
    title: "Machine Learning Engineer",
    category: "AI/ML",
    description: "JobClaw Demo",
    location: "Remote",
    isHot: false,
    applicationUrl: "https://example.com/apply/machine-learning-engineer",
    postedAt: "2026-06-06",
    source: "Company Careers",
    company: "JobClaw Demo",
  },
  {
    id: "mock-ai-intern",
    title: "AI Engineer Intern",
    category: "AI/ML",
    description: "JobClaw Demo",
    location: "Remote",
    isHot: false,
    applicationUrl: "https://example.com/apply/ai-engineer-intern",
    postedAt: "2026-06-06",
    source: "Company Careers",
    company: "JobClaw Demo",
  },
  {
    id: "mock-data-scientist",
    title: "Data Scientist",
    category: "Data",
    description: "JobClaw Demo",
    location: "Remote",
    isHot: false,
    applicationUrl: "https://example.com/apply/data-scientist",
    postedAt: "2026-06-05",
    source: "Company Careers",
    company: "JobClaw Demo",
  },
  {
    id: "mock-founding-ai-engineer",
    title: "Founding AI Engineer",
    category: "SWE",
    description: "JobClaw Demo",
    location: "San Francisco, CA",
    isHot: false,
    applicationUrl: "https://example.com/apply/founding-ai-engineer",
    postedAt: "2026-06-05",
    source: "Company Careers",
    company: "JobClaw Demo",
  },
  {
    id: "mock-product-designer",
    title: "Product Designer",
    category: "Other",
    description: "JobClaw Demo",
    location: "Remote",
    isHot: false,
    applicationUrl: "https://example.com/apply/product-designer",
    postedAt: "2026-06-04",
    source: "Company Careers",
    company: "JobClaw Demo",
  },
  {
    id: "mock-product-manager",
    title: "Product Manager",
    category: "Other",
    description: "JobClaw Demo",
    location: "New York, NY",
    isHot: false,
    applicationUrl: "https://example.com/apply/product-manager",
    postedAt: "2026-06-03",
    source: "Company Careers",
    company: "JobClaw Demo",
  },
  {
    id: "mock-growth-marketer",
    title: "Growth Marketer",
    category: "Other",
    description: "JobClaw Demo",
    location: "Remote",
    isHot: false,
    applicationUrl: "https://example.com/apply/growth-marketer",
    postedAt: "2026-06-02",
    source: "Company Careers",
    company: "JobClaw Demo",
  },
];

const API_BASE = "/api";
const BOARD_FRESHNESS_HOURS = 48;
const BOARD_REFRESH_INTERVAL_MS = 60 * 1000;
const ENABLE_MOCK_JOBS = process.env.NEXT_PUBLIC_ENABLE_MOCK_JOBS === "1";

function keywordText(job: ApiJob): string {
  return parseKeywordCategories(job.keywords_matched).join(" ");
}

function parseKeywordCategories(keywords: ApiJob["keywords_matched"]): string[] {
  if (!keywords) return [];
  if (Array.isArray(keywords)) return keywords.map(String).filter(Boolean);

  try {
    const parsed = JSON.parse(keywords);
    if (Array.isArray(parsed)) return parsed.map(String).filter(Boolean);
  } catch {
    // Fall through to delimiter parsing for older string payloads.
  }

  return keywords
    .split(/[,\n|]+/)
    .map((value) => value.replace(/[[\]"']/g, "").trim())
    .filter(Boolean);
}

function boardCategoryFromDiscord(category: DiscordJobCategory): BoardJobCategory {
  if (category === "AI/ML") return "AI/ML";
  if (category === "SWE") return "SWE";
  if (category === "Data Science" || category === "Data Engineering" || category === "Data Analyst") return "Data";
  return "Other";
}

function classifyCategory(job: ApiJob): BoardJob["category"] {
  const primaryDiscordCategory = parseKeywordCategories(job.keywords_matched).find((category): category is DiscordJobCategory =>
    DISCORD_JOB_CATEGORIES.has(category as DiscordJobCategory),
  );
  if (primaryDiscordCategory) return boardCategoryFromDiscord(primaryDiscordCategory);

  const text = `${job.title || ""} ${job.description || ""} ${keywordText(job)}`.toLowerCase();

  if (/\b(data scientist|decision scientist|analytics scientist|predictive modeler|statistical analyst)\b/.test(text)) {
    return "Data";
  }
  if (/\b(data engineer|analytics engineer|etl|data pipeline|data platform|data warehouse|lakehouse)\b/.test(text)) {
    return "Data";
  }
  if (/\b(data analyst|business intelligence analyst|bi analyst|reporting analyst|business analyst)\b/.test(text)) {
    return "Data";
  }
  if (/\b(ai|ml|machine learning|llm|research scientist|deep learning)\b/.test(text)) return "AI/ML";
  if (/\b(software engineer|software developer|frontend|backend|full stack|fullstack|devops|sre|infrastructure|platform engineer|mobile engineer|ios engineer|android engineer|security engineer)\b/.test(text)) {
    return "SWE";
  }

  return "Other";
}

function cleanLocation(location?: string): string {
  const raw = location?.replace(/\s+/g, " ").trim();
  if (!raw || /^(unknown|n\/a|none|null|not specified|location tbd)$/i.test(raw)) return "Remote";

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

function companyLabel(company: string | undefined, source: string): string {
  const raw = company?.replace(/\s+/g, " ").trim();
  if (!raw || /^(unknown|n\/a|none|null)$/i.test(raw)) return source;
  return raw.length > 72 ? `${raw.slice(0, 69).trim()}...` : raw;
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
    description: companyLabel(job.company, sourceLabel(job.source_ats)),
    location: cleanLocation(job.location),
    isHot: isHotJob(job),
    applicationUrl: job.url || "#",
    postedAt: job.date_posted || job.first_seen || new Date().toISOString(),
    source: sourceLabel(job.source_ats),
    company: job.company,
  };
}

async function fetchJobsWithParams(params: URLSearchParams): Promise<BoardJob[]> {
  const jobs: BoardJob[] = [];

  for (let page = 1; page <= 3; page += 1) {
    const pageParams = new URLSearchParams(params);
    pageParams.set("page", String(page));

    const response = await fetch(`${API_BASE}/jobs?${pageParams.toString()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`Jobs API ${response.status}`);

    const data = (await response.json()) as JobsResponse;
    jobs.push(...(data.jobs || []).map(mapApiJobToBoardJob).filter((job) => job.applicationUrl !== "#"));

    if (!data.has_more) break;
  }

  return jobs;
}

const NON_US_LOCATION_RE =
  /\b(canada|india|united kingdom|uk|england|scotland|wales|ireland|germany|france|spain|italy|netherlands|sweden|poland|portugal|australia|new zealand|singapore|japan|china|brazil|mexico|argentina|colombia|europe|emea|apac|latam)\b/i;
const US_LOCATION_RE =
  /\b(united states|usa|u\.s\.a\.|u\.s\.|us only|remote us|remote - us|remote \(us\)|america|north america|alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|florida|georgia|hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|maine|maryland|massachusetts|michigan|minnesota|mississippi|missouri|montana|nebraska|nevada|new hampshire|new jersey|new mexico|new york|north carolina|north dakota|ohio|oklahoma|oregon|pennsylvania|rhode island|south carolina|south dakota|tennessee|texas|utah|vermont|virginia|washington|west virginia|wisconsin|wyoming|washington dc|district of columbia|nyc|san francisco|los angeles|seattle|austin|boston|chicago|atlanta|denver|miami|dallas|houston|phoenix|portland|philadelphia|nashville|raleigh|charlotte|san diego|san jose)\b/i;
const US_STATE_CODE_RE =
  /(^|[\s,(/-])(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)(?=$|[\s,)/-])/;

function isUsLocation(location: string): boolean {
  const normalized = location.replace(/\s+/g, " ").trim();
  if (!normalized) return false;
  if (/^remote$/i.test(normalized)) return true;
  if (NON_US_LOCATION_RE.test(normalized)) return false;

  return US_LOCATION_RE.test(normalized) || US_STATE_CODE_RE.test(normalized);
}

function filterUsJobs(jobs: BoardJob[]): BoardJob[] {
  return jobs.filter((job) => isUsLocation(job.location));
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
    const acceptedJobs = filterUsJobs(await fetchJobsWithParams(acceptedParams));
    if (acceptedJobs.length) return { jobs: acceptedJobs, status: "real" };

    // Real fresh jobs are better than fake jobs while quality labels catch up.
    const freshJobs = filterUsJobs(await fetchJobsWithParams(new URLSearchParams(baseParams)));
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
