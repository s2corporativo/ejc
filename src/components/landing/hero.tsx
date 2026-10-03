"use client";

import { motion } from "framer-motion";
import { ArrowRight, Sparkles, ShieldCheck, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAppStore } from "@/lib/store";

export function Hero() {
  const { setView, setAuthOpen } = useAppStore();

  return (
    <section className="relative overflow-hidden border-b border-border">
      <div className="absolute inset-0 -z-10 bg-dot opacity-40" />
      <div className="absolute inset-x-0 top-0 -z-10 h-96 bg-gradient-to-b from-primary/10 via-transparent to-transparent" />
      <div className="absolute -right-32 top-10 -z-10 h-96 w-96 rounded-full bg-primary/15 blur-3xl animate-pulse-soft" />
      <div className="absolute -left-32 bottom-10 -z-10 h-80 w-80 rounded-full bg-accent/30 blur-3xl animate-pulse-soft" />

      <div className="container-juridia py-20 sm:py-28 lg:py-32">
        <div className="mx-auto max-w-4xl text-center">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="inline-flex items-center gap-2 rounded-full border border-border bg-secondary/60 px-3 py-1 text-xs font-medium text-muted-foreground"
          >
            <Sparkles className="h-3.5 w-3.5 text-primary" />
            <span>+ 35 milhões de minutas geradas</span>
            <span className="mx-1 h-1 w-1 rounded-full bg-muted-foreground/40" />
            <span>+ 90 mil usuários</span>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, delay: 0.05 }}
            className="mt-6 text-4xl font-bold tracking-tight text-balance sm:text-5xl lg:text-6xl"
          >
            O futuro do Direito brasileiro{" "}
            <span className="gradient-text">começa aqui</span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, delay: 0.12 }}
            className="mx-auto mt-6 max-w-2xl text-lg text-muted-foreground text-balance"
          >
            De petições a sentenças, a IA que mais entende — e mais produz —
            para o Direito brasileiro. Anonimização local (tarja-1),
            conformidade LGPD e Resolução CNJ 615/2025.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, delay: 0.18 }}
            className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row"
          >
            <Button
              size="lg"
              className="w-full sm:w-auto"
              onClick={() => setView("app")}
            >
              Conhecer a plataforma
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
            <Button
              size="lg"
              variant="outline"
              className="w-full sm:w-auto"
              onClick={() => setAuthOpen(true)}
            >
              Testar gratuitamente
            </Button>
          </motion.div>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5, delay: 0.28 }}
            className="mt-10 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs text-muted-foreground"
          >
            <div className="flex items-center gap-1.5">
              <ShieldCheck className="h-4 w-4 text-primary" />
              <span>Conformidade LGPD</span>
            </div>
            <div className="flex items-center gap-1.5">
              <ShieldCheck className="h-4 w-4 text-primary" />
              <span>Resolução CNJ 615/2025</span>
            </div>
            <div className="flex items-center gap-1.5">
              <FileText className="h-4 w-4 text-primary" />
              <span>AES-256 + TLS</span>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
