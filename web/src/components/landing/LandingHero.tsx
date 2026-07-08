import FeatureCards from "./FeatureCards";
import HeroBackground from "./HeroBackground";
import HeroCopy from "./HeroCopy";
import LandingHeader from "./LandingHeader";
import NotesBoard from "./NotesBoard";
import StatsStrip from "./StatsStrip";

export default function LandingHero() {
  return (
    <HeroBackground>
      <LandingHeader />
      <div className="pb-7 pt-8 lg:pt-[54px]">
        <div id="how-it-works" className="grid items-center gap-10 pb-8 xl:grid-cols-[0.92fr_1.25fr] xl:gap-16">
          <HeroCopy />
          <NotesBoard />
        </div>
        <StatsStrip />
        <FeatureCards />
        <p className="hidden pt-1 text-center font-serif text-base italic tracking-wide text-[#81745E] lg:block">
          Made for people who care about meaningful work. ♡
        </p>
      </div>
    </HeroBackground>
  );
}
