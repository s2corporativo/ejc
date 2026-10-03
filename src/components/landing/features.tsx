"use client";

import { motion } from "framer-motion";
import {
  Layers,
  FileStack,
  Search,
  PenLine,
  ShieldCheck,
  ScrollText,
} from "lucide-react";

const FEATURES = [
  {
    icon: Layers,
    title: "Múltiplos perfis integrados",
    desc: "Combinação automática de perfis de IA para cada etapa da geração — qualificação, fatos, fundamentos e pedidos.",
  },
  {
    icon: FileStack,
    title: "Processamento completo",
    desc: "Entende o inteiro teor do processo em uma única operação, extraindo informações relevantes.",
  },
  {
    icon: Search,
    title: "Jurisprudência inteligente",
    desc: "Encontre decisões relevantes com pesquisas assistidas por IA nos principais tribunais brasileiros.",
  },
  {
    icon: PenLine,
    title: "Aprendizado de estilo",
    desc: "Sistema único que aprende seu estilo individual de redação e reproduz sua identidade jurídica.",
  },
  {
    icon: ShieldCheck,
    title: "Conformidade LGPD",
    desc: "Uso de dados restrito à geração da minuta solicitada, sem retenção para outras finalidades.",
  },
  {
    icon: ScrollText,
    title: "Resolução CNJ 615/2025",
    desc: "Desenvolvido em conformidade com as diretrizes do Conselho Nacional de Justiça para IA no Judiciário.",
  },
];

export function Features() {
  return (
    <section id="recursos" className="border-b border-border">
      <div className="container-juridia py-20">
        <div className="mx-auto max-w-2xl text-center">
          <span className="text-sm font-semibold uppercase tracking-wider text-primary">
            Recursos
          </span>
          <h2 className="mt-2 text-3xl font-bold tracking-tight text-balance sm:text-4xl">
            Conheça o JuridIA e seus recursos
          </h2>
          <p className="mt-4 text-muted-foreground">
            O JuridIA é uma ferramenta que permite que você entregue o seu
            entendimento jurídico — único, humano e insubstituível — com mais
            qualidade e velocidade utilizando inteligência artificial.
          </p>
        </div>

        <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f, i) => (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, delay: i * 0.06 }}
              className="group relative rounded-xl border border-border bg-card p-6 transition-shadow hover:shadow-md"
            >
              <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary transition-transform group-hover:scale-105">
                <f.icon className="h-5 w-5" />
              </div>
              <h3 className="text-lg font-semibold">{f.title}</h3>
              <p className="mt-2 text-sm text-muted-foreground">{f.desc}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
