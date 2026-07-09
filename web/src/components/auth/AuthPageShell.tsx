import Link from "next/link";
import AuthPanel from "@/components/auth/AuthPanel";
import NoriMark from "@/components/landing/NoriMark";

export default function AuthPageShell({
    mode,
    title,
    copy,
}: {
    mode: "login" | "signup";
    title: string;
    copy: string;
}) {
    return (
        <main className="relative min-h-screen overflow-hidden bg-[#FBF4E7] px-5 py-7 text-[#1F281B] [background-image:radial-gradient(circle_at_14%_16%,rgba(215,234,220,0.62),transparent_28%),radial-gradient(circle_at_82%_20%,rgba(246,218,158,0.52),transparent_30%),linear-gradient(135deg,#FBF4E7_0%,#F8ECD7_100%)]">
            <div className="pointer-events-none absolute -left-16 bottom-[-90px] h-72 w-56 -rotate-12 rounded-[28px] border border-[#526736]/30 bg-[#526736] opacity-90 shadow-[0_24px_60px_rgba(70,45,16,0.18)] [background-image:linear-gradient(rgba(82,103,54,0.45),rgba(82,103,54,0.45)),url('/nori-assets/notebook-texture.png')] [background-size:cover]" />
            <div className="pointer-events-none absolute -right-8 top-32 h-72 w-44 opacity-35">
                <div className="h-full w-full [background-image:url('/nori-assets/dried-flowers.png')] [background-size:contain] [background-repeat:no-repeat]" />
            </div>

            <div className="relative mx-auto flex min-h-[calc(100vh-3.5rem)] max-w-5xl flex-col">
                <header className="flex items-center justify-between rounded-[24px] border border-[#E7D7B7] bg-[#FFF9EC]/78 px-5 py-4 shadow-[0_18px_48px_rgba(83,61,28,0.10)] backdrop-blur-md">
                    <Link href="/" className="flex items-center gap-3" aria-label="Nori home">
                        <NoriMark />
                        <span className="font-serif text-[34px] font-bold leading-none tracking-[-0.04em] text-[#1F281B]">Nori</span>
                    </Link>
                </header>

                <section className="grid flex-1 place-items-center py-10">
                    <div className="w-full max-w-[460px]">
                        <div className="mb-5 text-center">
                            <p className="mb-3 text-xs font-black uppercase tracking-[0.22em] text-[#526736]">Nori account</p>
                            <h1 className="font-serif text-[42px] font-bold leading-none tracking-[-0.06em] text-[#12302A] sm:text-[52px]">{title}</h1>
                            <p className="mx-auto mt-3 max-w-md text-sm font-medium leading-6 text-[#5F665C]">{copy}</p>
                        </div>
                        <AuthPanel initialMode={mode} redirectTo="/jobs" />
                    </div>
                </section>
            </div>
        </main>
    );
}
