import type { BoardDataStatus } from "@/lib/job-board";

interface RefreshInfoProps {
  lastRefreshed: string | null;
  status: BoardDataStatus;
}

function formatRefreshTime(value: string | null): string {
  if (!value) return "Checking...";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Recently";

  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function statusText(status: BoardDataStatus): string | null {
  if (status === "mock") return "Preview data";
  if (status === "unavailable") return "Connecting to JobClaw API";
  if (status === "empty") return "No fresh jobs yet";
  return null;
}

export default function RefreshInfo({ lastRefreshed, status }: RefreshInfoProps) {
  const label = statusText(status);

  return (
    <div className="flex flex-wrap justify-center gap-x-3 gap-y-1 text-xs font-medium text-zinc-500 sm:text-sm">
      <span className="text-zinc-700">Showing jobs from the last 48 hours</span>
      <span className="hidden h-1 w-1 self-center rounded-full bg-zinc-300 sm:block" aria-hidden="true" />
      <span>Last refreshed: {formatRefreshTime(lastRefreshed)}</span>
      {label && (
        <>
          <span className="hidden h-1 w-1 self-center rounded-full bg-zinc-300 sm:block" aria-hidden="true" />
          <span>{label}</span>
        </>
      )}
    </div>
  );
}
