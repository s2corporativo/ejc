"use client";

import { motion } from "framer-motion";
import { ArrowRight, ShieldCheck, FileText, Scale } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAppStore } from "@/lib/store";

export function Hero() {
  const { setView, setAppTab } = useAppStore();

  return (
    <section className="relative overflow-hidden border-b border-border">
      {/* Background */}
      <div className="absolute inset-0 -z-10 bg-dot opacity-30" />
      <div className="absolute inset-x-0 top-0 -z-10 h-96 bg-gradient-to-b from-primary/10 via-transparent to-transparent" />
      <motion.div
        animate={{ x: [0, 30, 0], y: [0, 20, 0], scale: [1, 1.1, 1] }}
        transition={{ duration: 12, repeat: Infinity, ease: "easeInOut" }}
        className="absolute -right-32 top-10 -z-10 h-96 w-96 rounded-full bg-primary/15 blur-3xl"
      />
      <motion.div
        animate={{ x: [0, -40, 0], y: [0, -30, 0], scale: [1, 1.15, 1] }}
        transition={{ duration: 15, repeat: Infinity, ease: "easeInOut", delay: 2 }}
        className="absolute -left-32 bottom-10 -z-10 h-80 w-80 rounded-full bg-accent/30 blur-3xl"
      />

      <div className="container-juridia py-16 sm:py-20 lg:py-24">
        <div className="mx-auto max-w-4xl text-center">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="inline-flex items-center gap-2 rounded-full border border-border bg-secondary/60 px-3 py-1 text-xs font-medium text-muted-foreground"
          >
            <Scale className="h-3.5 w-3.5 text-primary" />
            <span>Assistente jurídico do seu escritório</span>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, delay: 0.05 }}
            className="mt-6 text-4xl font-bold tracking-tight text-balance sm:text-5xl lg:text-6xl"
          >
            Gere minutas jurídicas com{" "}
            <span className="gradient-text">IA e sigilo</span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, delay: 0.12 }}
            className="mx-auto mt-6 max-w-2xl text-lg text-muted-foreground text-balance"
          >
            Petições, sentenças, contratos e pareceres redigidos por IA, com
            anonimização local dos dados sensíveis (tarja-1). Conformidade LGPD
            e Resolução CNJ 615/2025. Para uso interno do seu escritório.
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
              onClick={() => {
                setView("app");
                setAppTab("generator");
              }}
            >
              Gerar minuta agora
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
            <Button
              size="lg"
              variant="outline"
              className="w-full sm:w-auto"
              onClick={() => {
                setView("app");
                setAppTab("dashboard");
              }}
            >
              Ver início
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
              <span>Anonimização local (tarja-1)</span>
            </div>
            <div className="flex items-center gap-1.5">
              <ShieldCheck className="h-4 w-4 text-primary" />
              <span>Conformidade LGPD</span>
            </div>
            <div className="flex items-center gap-1.5">
              <FileText className="h-4 w-4 text-primary" />
              <span>Resolução CNJ 615/2025</span>
            </div>
            <div className="flex items-center gap-1.5">
              <ShieldCheck className="h-4 w-4 text-primary" />
              <span>Sem treinar IA com seus dados</span>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
