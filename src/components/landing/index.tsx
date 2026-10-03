"use client";

import { Hero } from "./hero";
import { Stats } from "./stats";
import { HowItWorks } from "./how-it-works";
import { Features } from "./features";
import { Anonymization } from "./anonymization";
import { Privacy } from "./privacy";
import { Integrations } from "./integrations";
import { Faq } from "./faq";

export function Landing() {
  return (
    <>
      <Hero />
      <HowItWorks />
      <Features />
      <Anonymization />
      <Privacy />
      <Faq />
    </>
  );
}
