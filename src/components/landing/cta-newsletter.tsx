"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { ArrowRight, Mail, CheckCircle2, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "@/hooks/use-toast";
import { useAppStore } from "@/lib/store";

export function CtaNewsletter() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const { setView, setAuthOpen } = useAppStore();

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim() || !email.includes("@")) {
      toast({ title: "E-mail inválido", variant: "destructive" });
      return;
    }
    setSubmitted(true);
    toast({
      title: "Inscrição confirmada!",
      description: "Você receberá novidades do JuridIA no e-mail informado.",
    });
    setEmail("");
  }

  return (
    <section id="cta" className="border-b border-border bg-gradient-to-br from-primary/5 via-background to-accent/10">
      <div className="container-juridia py-20">
        <div className="mx-auto max-w-4xl">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            className="overflow-hidden rounded-2xl border border-border bg-card shadow-lg"
          >
            <div className="grid gap-0 md:grid-cols-2">
              {/* Left: CTA */}
              <div className="relative p-8 sm:p-10">
                <div className="absolute -right-8 -top-8 h-32 w-32 rounded-full bg-primary/10 blur-2xl" />
                <div className="relative">
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-secondary/60 px-3 py-1 text-xs font-medium">
                    <Sparkles className="h-3 w-3 text-primary" />
                    Comece grátis hoje
                  </span>
                  <h2 className="mt-4 text-2xl font-bold tracking-tight sm:text-3xl">
                    Pronto para acelerar sua advocacia?
                  </h2>
                  <p className="mt-3 text-sm text-muted-foreground">
                    Teste o JuridIA gratuitamente. Sem cartão de crédito.
                    Gere sua primeira minuta em minutos.
                  </p>
                  <div className="mt-5 flex flex-col gap-2 sm:flex-row">
                    <Button
                      size="lg"
                      className="w-full sm:w-auto"
                      onClick={() => setAuthOpen(true)}
                    >
                      Testar gratuitamente
                      <ArrowRight className="ml-2 h-4 w-4" />
                    </Button>
                    <Button
                      size="lg"
                      variant="outline"
                      className="w-full sm:w-auto"
                      onClick={() => setView("app")}
                    >
                      Ver plataforma
                    </Button>
                  </div>
                  <div className="mt-5 flex flex-wrap gap-3 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <CheckCircle2 className="h-3.5 w-3.5 text-primary" /> 3 minutas grátis
                    </span>
                    <span className="flex items-center gap-1">
                      <CheckCircle2 className="h-3.5 w-3.5 text-primary" /> Sem cartão
                    </span>
                    <span className="flex items-center gap-1">
                      <CheckCircle2 className="h-3.5 w-3.5 text-primary" /> LGPD compliant
                    </span>
                  </div>
                </div>
              </div>

              {/* Right: Newsletter */}
              <div className="border-t border-border bg-secondary/30 p-8 sm:p-10 md:border-l md:border-t-0">
                <div className="flex h-full flex-col justify-center">
                  <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                    <Mail className="h-5 w-5" />
                  </div>
                  <h3 className="text-lg font-semibold">
                    Receba novidades do JuridIA
                  </h3>
                  <p className="mt-1.5 text-sm text-muted-foreground">
                    Novos recursos, templates e atualizações da Resolução CNJ.
                    Um e-mail por mês, sem spam.
                  </p>
                  {submitted ? (
                    <div className="mt-5 flex items-center gap-3 rounded-lg border border-primary/30 bg-primary/5 p-4">
                      <CheckCircle2 className="h-5 w-5 text-primary" />
                      <div>
                        <div className="text-sm font-semibold">Inscrição confirmada!</div>
                        <div className="text-xs text-muted-foreground">
                          Obrigado por se inscrever.
                        </div>
                      </div>
                    </div>
                  ) : (
                    <form onSubmit={submit} className="mt-5 space-y-2">
                      <Input
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="voce@escritorio.com.br"
                        required
                      />
                      <Button type="submit" className="w-full">
                        Inscrever-se
                      </Button>
                      <p className="text-[11px] text-muted-foreground">
                        Ao se inscrever, você concorda com nossa Política de Privacidade.
                      </p>
                    </form>
                  )}
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
