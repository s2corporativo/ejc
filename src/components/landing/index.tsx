"use client";

import { Hero } from "./hero";
import { Stats } from "./stats";
import { Features } from "./features";
import { Anonymization } from "./anonymization";
import { Privacy } from "./privacy";
import { Integrations } from "./integrations";
import { News } from "./news";
import { Pricing } from "./pricing";
import { Media } from "./media";

export function Landing() {
  return (
    <>
      <Hero />
      <Stats />
      <Features />
      <Anonymization />
      <Privacy />
      <Integrations />
      <News />
      <Pricing />
      <Media />
    </>
  );
}
