"use client";

import { Hero } from "./hero";
import { Stats } from "./stats";
import { HowItWorks } from "./how-it-works";
import { Features } from "./features";
import { Anonymization } from "./anonymization";
import { Privacy } from "./privacy";
import { Integrations } from "./integrations";
import { Testimonials } from "./testimonials";
import { News } from "./news";
import { Pricing } from "./pricing";
import { Faq } from "./faq";
import { CtaNewsletter } from "./cta-newsletter";
import { Media } from "./media";

export function Landing() {
  return (
    <>
      <Hero />
      <Stats />
      <HowItWorks />
      <Features />
      <Anonymization />
      <Privacy />
      <Integrations />
      <Testimonials />
      <News />
      <Pricing />
      <Faq />
      <CtaNewsletter />
      <Media />
    </>
  );
}
