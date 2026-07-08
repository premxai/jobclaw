import Image from "next/image";

const features = [
  {
    number: "01",
    title: "Quiet monitoring",
    text: "Nori checks thousands of company career pages and ATS boards, 24/7, so you can focus on what matters.",
    image: "/nori-assets/feature-telescope.svg",
  },
  {
    number: "02",
    title: "Clean notes",
    text: "We turn noise into clarity. Only fresh, relevant, direct-apply roles delivered as beautiful daily notes.",
    image: "/nori-assets/feature-notes.svg",
  },
  {
    number: "03",
    title: "Fast apply tracking",
    text: "Save, apply, and track progress in one place. Know what's done and what's next.",
    image: "/nori-assets/feature-tracking.svg",
  },
];

export default function FeatureCards() {
  return (
    <section id="features" className="relative z-10 mt-[34px] grid gap-7 pb-6 lg:grid-cols-3">
      {features.map((feature) => (
        <article key={feature.title} className="relative flex min-h-[188px] items-center overflow-hidden rounded-[20px] border border-[#E7D7B7] bg-[#FFF9EC]/82 px-8 py-7 shadow-[0_10px_24px_rgba(70,45,16,0.07)] backdrop-blur lg:px-[34px]">
          <div className="grid w-full items-center gap-7 sm:grid-cols-[120px_1fr]">
            <div className="relative h-[120px] w-[120px] overflow-hidden rounded-[22px] border border-[#E7D7B7] bg-[#FFF7E5] shadow-[0_8px_18px_rgba(70,45,16,0.06)]">
              <Image src={feature.image} alt="" aria-hidden="true" fill sizes="120px" className="object-cover" />
            </div>
            <div>
              <h3 className="mb-2.5 font-serif text-[26px] font-bold leading-[1.1] tracking-[-0.04em] text-[#1F281B]">{feature.title}</h3>
              <p className="max-w-[310px] text-[14.5px] font-medium leading-[1.5] text-[#5F665C]">{feature.text}</p>
            </div>
          </div>
          <span className="absolute right-7 top-6 grid h-[26px] w-[38px] place-items-center rounded-[9px] bg-[#526736] text-xs font-bold text-[#FFF9EC]">{feature.number}</span>
        </article>
      ))}
    </section>
  );
}
