"use client";

import { motion } from "framer-motion";
import { Chrome, FileSearch, Zap, MousePointerClick, ClipboardList, Layers } from "lucide-react";
import { Button } from "@/components/ui/button";

const SYSTEMS = ["PJe", "SEEU", "Eproc", "STF", "Projudi", "STJ", "e-SAJ", "SEI", "JPe"];

const FEATURES = [
  { icon: FileSearch, title: "OCR", desc: "Documentos digitalizados ou imagens não são mais um problema." },
  { icon: Zap, title: "Exportação do inteiro teor", desc: "Exportação do inteiro teor completo para o JuridIA com um único clique." },
  { icon: MousePointerClick, title: "Ações rápidas", desc: "Menu de contexto com ações rápidas para o editor." },
  { icon: ClipboardList, title: "Buffer inteligente", desc: "Acumule trechos do processo e organize antes de inserir na minuta." },
  { icon: Layers, title: "Fluxo contínuo", desc: "Conecte seu trabalho no tribunal diretamente ao editor do JuridIA com um clique." },
];

export function Integrations() {
  return (
    <section className="border-b border-border bg-secondary/30">
      <div className="container-juridia py-20">
        <div className="mx-auto max-w-2xl text-center">
          <span className="text-sm font-semibold uppercase tracking-wider text-primary">
            Conecta
          </span>
          <h2 className="mt-2 text-3xl font-bold tracking-tight text-balance sm:text-4xl">
            A inteligência do JuridIA conectada aos principais sistemas
          </h2>
          <p className="mt-4 text-muted-foreground">
            Universalidade real. A extensão com suporte aos principais sistemas
            de processos eletrônicos do Brasil.
          </p>
        </div>

        <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
          {SYSTEMS.map((s, i) => (
            <motion.div
              key={s}
              initial={{ opacity: 0, scale: 0.9 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ duration: 0.3, delay: i * 0.04 }}
              className="rounded-lg border border-border bg-card px-4 py-2 text-sm font-semibold text-muted-foreground"
            >
              {s}
            </motion.div>
          ))}
        </div>

        <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f, i) => (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 14 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, delay: i * 0.06 }}
              className="rounded-xl border border-border bg-card p-5"
            >
              <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <f.icon className="h-5 w-5" />
              </div>
              <h3 className="font-semibold">{f.title}</h3>
              <p className="mt-1.5 text-sm text-muted-foreground">{f.desc}</p>
            </motion.div>
          ))}
        </div>

        <div className="mt-10 flex justify-center">
          <Button size="lg" variant="outline">
            <Chrome className="mr-2 h-4 w-4" />
            Instalar Extensão
          </Button>
        </div>
        <p className="mt-3 text-center text-xs text-muted-foreground">
          Compatível com Chrome em Windows e MacOS
        </p>
      </div>
    </section>
  );
}
