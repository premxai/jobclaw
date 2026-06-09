import JobBoard from "@/components/job-board/JobBoard";

export default function HomePage() {
  return (
    <main className="jobclaw-home-bg relative h-[100dvh] min-h-[100svh] overflow-hidden bg-[#fff4e2] bg-no-repeat text-zinc-950">
      {/* The background lives on <main> and stays fixed to the viewport.
          This inner layer scrolls when the board can't fit a short screen. */}
      <div className="h-full overflow-y-auto overflow-x-hidden overscroll-contain">
        <JobBoard />
      </div>
    </main>
  );
}
