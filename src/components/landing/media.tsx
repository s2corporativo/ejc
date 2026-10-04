"use client";

import { motion } from "framer-motion";
import { Newspaper } from "lucide-react";

const MEDIA = [
  { source: "Época Negócios", date: "1 de setembro de 2026", title: "O que é a JuridIA, ferramenta de IA que vai ajudar juízes a elaborar decisões", excerpt: "Integrada a sistemas internos do Tribunal de Justiça, plataforma analisa documentos e prepara propostas de textos jurídicos." },
  { source: "Radar Digital Brasília", date: "30 de junho de 2025", title: "Tribunal adota solução de IA para criação de minutas jurídicas", excerpt: "A solução de inteligência artificial generativa é voltada à automação de minutas jurídicas." },
  { source: "Fairmind", date: "27 de agosto de 2026", title: "Legaltech consolidada em inteligência artificial jurídica", excerpt: "Plataforma com receita recorrente anual, consolidando liderança em inteligência artificial para o Direito." },
];

export function Media() {
  return (
    <section id="midia" className="border-b border-border">
      <div className="container-juridia py-20">
        <div className="mx-auto max-w-2xl text-center">
          <span className="text-sm font-semibold uppercase tracking-wider text-primary">
            Na mídia
          </span>
          <h2 className="mt-2 text-3xl font-bold tracking-tight text-balance sm:text-4xl">
            O que dizem sobre a revolução do JuridIA no Direito brasileiro
          </h2>
        </div>

        <div className="mt-12 grid gap-5 md:grid-cols-3">
          {MEDIA.map((m, i) => (
            <motion.article
              key={m.source}
              initial={{ opacity: 0, y: 14 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, delay: i * 0.08 }}
              className="flex flex-col rounded-xl border border-border bg-card p-6 transition-shadow hover:shadow-md"
            >
              <Newspaper className="mb-3 h-6 w-6 text-primary" />
              <div className="text-xs text-muted-foreground">{m.date}</div>
              <h3 className="mt-2 font-semibold leading-tight">{m.title}</h3>
              <p className="mt-2 flex-1 text-sm text-muted-foreground">
                {m.excerpt}
              </p>
              <div className="mt-4 text-xs font-semibold uppercase tracking-wider text-primary">
                {m.source}
              </div>
            </motion.article>
          ))}
        </div>
      </div>
    </section>
  );
}
