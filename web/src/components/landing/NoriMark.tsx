import Image from "next/image";

export default function NoriMark() {
  return (
    <span className="relative grid h-11 w-11 shrink-0 place-items-center overflow-visible">
      <Image
        src="/nori-assets/nori-mark.png"
        alt=""
        aria-hidden="true"
        fill
        sizes="44px"
        className="h-full w-full scale-[1.62] object-contain drop-shadow-[0_8px_14px_rgba(81,67,38,0.16)]"
      />
    </span>
  );
}
