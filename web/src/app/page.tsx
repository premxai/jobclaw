import JobBoard from "@/components/job-board/JobBoard";

export default function HomePage() {
  return (
    <main
      className="jobclaw-home-bg overflow-hidden bg-[#f6e8cc] bg-no-repeat text-zinc-950"
      style={{
        backgroundImage: "url('/images/jobclaw-room-bg.png')",
        height: "100dvh",
        minHeight: "100svh",
      }}
    >
      <JobBoard />
    </main>
  );
}
