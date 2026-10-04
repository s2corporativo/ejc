"use client";

import { motion } from "framer-motion";
import { Star, Quote } from "lucide-react";
import { Badge } from "@/components/ui/badge";

interface Testimonial {
  name: string;
  role: string;
  location: string;
  text: string;
  rating: number;
  initials: string;
}

const TESTIMONIALS: Testimonial[] = [
  {
    name: "Dra. Camila R.",
    role: "Advogada Sênior",
    location: "São Paulo/SP",
    text: "A anonimização local (tarja-1) mudou minha rotina. Atendo casos sigilosos e nunca mais precisei digitar dados sensíveis manualmente em cada peça. Em uma semana, reduzi 70% do tempo de redação.",
    rating: 5,
    initials: "CR",
  },
  {
    name: "Dr. Henrique M.",
    role: "Procurador Municipal",
    location: "Belo Horizonte/MG",
    text: "A geração em lote com etapas nos poupa centenas de horas por mês. Aprovo a primeira minuta e a IA replica o estilo para os demais processos. Conformidade CNJ 615/2025 impecável.",
    rating: 5,
    initials: "HM",
  },
  {
    name: "Dra. Patrícia L.",
    role: "Sócia de Escritório",
    location: "Porto Alegre/RS",
    text: "As habilidades (skills) são o diferencial. Posso fixar as inegociáveis com # e ainda editar com meu entendimento. A IA aprende meu estilo de redação de verdade.",
    rating: 5,
    initials: "PL",
  },
  {
    name: "Dr. Robson A.",
    role: "Defensor Público",
    location: "Salvador/BA",
    text: "O JurisprudênciaIA é impressionante. Descrevo o caso em linguagem natural e ele encontra precedentes que nem passavam pela minha pesquisa tradicional. A combinação BM25 + embeddings funciona.",
    rating: 5,
    initials: "RA",
  },
  {
    name: "Dra. Fernanda T.",
    role: "Advogada Trabalhista",
    location: "Curitiba/PR",
    text: "Antes eu levava 2 horas para redigir uma reclamação trabalhista. Hoje, com o JuridIA, em 15 minutos tenho a peça pronta para revisão. Mais tempo para me dedicar à estratégia do caso.",
    rating: 5,
    initials: "FT",
  },
  {
    name: "Dr. Marcelo B.",
    role: "Advogado Tributarista",
    location: "Rio de Janeiro/RJ",
    text: "Usei para defesa fiscal em lote (300+ autos). A economia de tempo foi absurda. As skills do CTN garantiram fundamentação consistente em todas as peças. Cliente aprovou sem ressalvas.",
    rating: 5,
    initials: "MB",
  },
];

export function Testimonials() {
  return (
    <section id="depoimentos" className="border-b border-border">
      <div className="container-juridia py-20">
        <div className="mx-auto max-w-2xl text-center">
          <Badge variant="secondary" className="mb-3">
            <Star className="mr-1 h-3 w-3 fill-current" /> Depoimentos
          </Badge>
          <h2 className="mt-2 text-3xl font-bold tracking-tight text-balance sm:text-4xl">
            Advogados que já transformaram sua rotina
          </h2>
          <p className="mt-4 text-muted-foreground">
            +90 mil profissionais do Direito brasileiro usam o JuridIA diariamente.
            Veja o que dizem sobre a experiência.
          </p>
        </div>

        <div className="mt-12 columns-1 gap-5 sm:columns-2 lg:columns-3 [&>*]:mb-5 [&>*]:break-inside-avoid">
          {TESTIMONIALS.map((t, i) => (
            <motion.div
              key={t.name}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, delay: (i % 3) * 0.08 }}
              className="rounded-xl border border-border bg-card p-5 transition-shadow hover:shadow-md"
            >
              <div className="mb-3 flex items-start justify-between">
                <div className="flex gap-0.5">
                  {Array.from({ length: t.rating }).map((_, idx) => (
                    <Star
                      key={idx}
                      className="h-4 w-4 fill-amber-500 text-amber-500"
                    />
                  ))}
                </div>
                <Quote className="h-6 w-6 text-muted-foreground/30" />
              </div>
              <p className="text-sm leading-relaxed text-foreground/90">
                “{t.text}”
              </p>
              <div className="mt-4 flex items-center gap-3 border-t border-border pt-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-sm font-bold text-primary">
                  {t.initials}
                </div>
                <div>
                  <div className="text-sm font-semibold">{t.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {t.role} · {t.location}
                  </div>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
