import JobBoard from "@/components/job-board/JobBoard";

export default function HomePage() {
  return (
    <main
      className="h-screen overflow-hidden bg-[#f6e8cc] bg-cover bg-center bg-no-repeat text-zinc-950"
      style={{ backgroundImage: "url('/images/jobclaw-room-bg.png')" }}
    >
      <JobBoard />
    </main>
  );
}
