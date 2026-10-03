"use client";

import { motion } from "framer-motion";
import { PenLine, Cpu, Sparkles, FileCheck } from "lucide-react";

const STEPS = [
  {
    icon: PenLine,
    step: "01",
    title: "Descreva o caso",
    desc: "Preencha o template com os fatos, partes e pedidos. Use dados reais — a IA nunca os vê.",
  },
  {
    icon: Cpu,
    step: "02",
    title: "Anonimização local",
    desc: "O tarja-1 detecta CPFs, nomes e valores e substitui por marcadores antes de qualquer dado sair da sua máquina.",
  },
  {
    icon: Sparkles,
    step: "03",
    title: "IA gera a minuta",
    desc: "Múltiplos perfis de IA combinam com as habilidades (skills) jurídicas para redigir a peça completa.",
  },
  {
    icon: FileCheck,
    step: "04",
    title: "Receba e revise",
    desc: "A desanonimização restaura os dados localmente. Você revisa no editor, com sugestões de IA e export PDF.",
  },
];

export function HowItWorks() {
  return (
    <section id="como-funciona" className="border-b border-border">
      <div className="container-juridia py-20">
        <div className="mx-auto max-w-2xl text-center">
          <span className="text-sm font-semibold uppercase tracking-wider text-primary">
            Como funciona
          </span>
          <h2 className="mt-2 text-3xl font-bold tracking-tight text-balance sm:text-4xl">
            Da descrição à minuta em 4 passos
          </h2>
          <p className="mt-4 text-muted-foreground">
            Um fluxo projetado para respeitar o sigilo profissional do
            advogado e a privacidade dos dados do cliente.
          </p>
        </div>

        <div className="relative mt-14">
          {/* Linha conectora */}
          <div className="absolute left-0 right-0 top-12 hidden h-px bg-gradient-to-r from-transparent via-border to-transparent lg:block" />

          <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s, i) => (
              <motion.div
                key={s.step}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.4, delay: i * 0.1 }}
                className="relative flex flex-col items-center text-center"
              >
                <div className="relative z-10 mb-4 flex h-24 w-24 items-center justify-center rounded-full border-2 border-primary/20 bg-card">
                  <div className="flex h-16 w-16 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg">
                    <s.icon className="h-7 w-7" />
                  </div>
                  <span className="absolute -right-1 -top-1 flex h-7 w-7 items-center justify-center rounded-full bg-accent text-xs font-bold text-accent-foreground ring-2 ring-card">
                    {s.step}
                  </span>
                </div>
                <h3 className="text-lg font-semibold">{s.title}</h3>
                <p className="mt-2 text-sm text-muted-foreground">{s.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
