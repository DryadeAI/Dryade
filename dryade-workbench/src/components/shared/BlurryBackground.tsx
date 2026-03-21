// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import dryadeLogo from "@/assets/dryade-logo.svg";

const BlurryBackground = () => {
  return (
    <div
      className="fixed inset-0 md:left-[var(--sidebar-width,13rem)] lg:right-[var(--right-panel-width,0px)] overflow-hidden pointer-events-none -z-10 motion-safe:transition-[left,right] motion-safe:duration-300 ease-in-out"
      style={{ willChange: "left, right" }}
    >
      <img
        src={dryadeLogo}
        alt=""
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[64%] h-[64%] object-contain opacity-[0.025] dark:opacity-[0.06] blur-md invert dark:invert-0"
        aria-hidden="true"
      />
    </div>
  );
};

export default BlurryBackground;
