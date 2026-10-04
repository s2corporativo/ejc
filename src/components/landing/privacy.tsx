"use client";

import { motion } from "framer-motion";
import { EyeOff, Lock, Database, Settings } from "lucide-react";
import { Badge } from "@/components/ui/badge";

const PILLARS = [
  {
    icon: EyeOff,
    title: "Inacessível até para nós",
    desc: "Nem mesmo a equipe do JuridIA consegue visualizar o conteúdo das suas minutas ou dados processuais.",
  },
  {
    icon: Lock,
    title: "Criptografia em trânsito e repouso",
    desc: "TLS para dados em trânsito e AES-256 para dados armazenados — padrão bancário de segurança.",
  },
  {
    icon: Database,
    title: "Sem treinamento de IA",
    desc: "Seus dados nunca são usados para treinar ou aprimorar modelos de inteligência artificial.",
  },
  {
    icon: Settings,
    title: "Controle total dos seus dados",
    desc: "Você pode manter ou excluir suas minutas e dados a qualquer momento — o controle é sempre seu.",
  },
];

export function Privacy() {
  return (
    <section className="border-b border-border">
      <div className="container-juridia py-20">
        <div className="grid gap-12 lg:grid-cols-2 lg:items-center">
          <div>
            <Badge variant="secondary" className="mb-3">
              <Lock className="mr-1 h-3 w-3" /> Privacidade
            </Badge>
            <h2 className="text-3xl font-bold tracking-tight text-balance sm:text-4xl">
              Sua minuta pertence apenas a você
            </h2>
            <p className="mt-4 text-muted-foreground">
              Construímos o JuridIA sob o princípio de que o advogado é o
              guardião dos dados do seu cliente. Toda a arquitetura foi pensada
              para que nem mesmo a nossa equipe tenha acesso ao conteúdo real.
            </p>
            <div className="mt-6 rounded-xl border border-dashed border-border bg-secondary/40 p-4 text-sm text-muted-foreground">
              <strong className="text-foreground">Plano Enterprise:</strong>{" "}
              escritórios e departamentos jurídicos podem optar por dados 100%
              segregados e infraestrutura dedicada.
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {PILLARS.map((p, i) => (
              <motion.div
                key={p.title}
                initial={{ opacity: 0, y: 14 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.4, delay: i * 0.06 }}
                className="rounded-xl border border-border bg-card p-5"
              >
                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <p.icon className="h-5 w-5" />
                </div>
                <h3 className="font-semibold">{p.title}</h3>
                <p className="mt-1.5 text-sm text-muted-foreground">{p.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
