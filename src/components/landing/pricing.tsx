"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Check, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAppStore } from "@/lib/store";
import { toast } from "@/hooks/use-toast";

const PLANS = [
  {
    id: "individual_1",
    name: "Individual I",
    price: 140,
    minutas: 100,
    conecta: 100,
    perks: ["Pagamento à vista", "Renovação automática"],
    highlight: false,
  },
  {
    id: "individual_2",
    name: "Individual II",
    price: 280,
    minutas: 200,
    conecta: 200,
    perks: ["Pagamento à vista", "Renovação automática", "Treinamento individual online (mediante agendamento)"],
    highlight: true,
  },
  {
    id: "individual_3",
    name: "Individual III",
    price: 560,
    minutas: 400,
    conecta: 400,
    perks: ["Pagamento à vista", "Renovação automática", "Treinamento individual online", "Suporte prioritário", "Acesso antecipado a novas funcionalidades"],
    highlight: false,
  },
];

const DISCOUNTS: Record<string, number> = { mensal: 0, semestral: 0.1, anual: 0.25 };

export function Pricing() {
  const [billing, setBilling] = useState<"mensal" | "semestral" | "anual">("mensal");
  const [kind, setKind] = useState<"individual" | "corporativo" | "enterprise">("individual");
  const { setView } = useAppStore();

  return (
    <section id="planos" className="border-b border-border bg-secondary/30">
      <div className="container-juridia py-20">
        <div className="mx-auto max-w-2xl text-center">
          <span className="text-sm font-semibold uppercase tracking-wider text-primary">
            Planos
          </span>
          <h2 className="mt-2 text-3xl font-bold tracking-tight text-balance sm:text-4xl">
            Escolha seu plano
          </h2>
          <p className="mt-4 text-muted-foreground">
            Individual, corporativo ou enterprise. Comece pequeno e evolua conforme sua operação cresce.
          </p>
        </div>

        <div className="mt-10 flex flex-col items-center gap-6">
          <Tabs value={kind} onValueChange={(v) => setKind(v as typeof kind)}>
            <TabsList>
              <TabsTrigger value="individual">individual</TabsTrigger>
              <TabsTrigger value="corporativo">corporativo</TabsTrigger>
              <TabsTrigger value="enterprise">enterprise</TabsTrigger>
            </TabsList>
          </Tabs>

          <ToggleGroup
            type="single"
            value={billing}
            onValueChange={(v) => v && setBilling(v as typeof billing)}
            className="rounded-lg border border-border bg-card p-1"
          >
            <ToggleGroupItem value="mensal" className="px-4 text-sm">mensal</ToggleGroupItem>
            <ToggleGroupItem value="semestral" className="px-4 text-sm">
              semestral <Badge className="ml-2" variant="secondary">-10%</Badge>
            </ToggleGroupItem>
            <ToggleGroupItem value="anual" className="px-4 text-sm">
              anual <Badge className="ml-2" variant="secondary">-25%</Badge>
            </ToggleGroupItem>
          </ToggleGroup>
        </div>

        {kind === "individual" && (
          <div className="mt-12 grid gap-6 lg:grid-cols-3">
            {PLANS.map((p, i) => {
              const finalPrice = Math.round(p.price * (1 - DISCOUNTS[billing]));
              return (
                <motion.div
                  key={p.id}
                  initial={{ opacity: 0, y: 16 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.4, delay: i * 0.06 }}
                  className={`relative flex flex-col rounded-xl border bg-card p-6 ${
                    p.highlight ? "border-primary shadow-lg ring-1 ring-primary/30" : "border-border"
                  }`}
                >
                  {p.highlight && (
                    <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                      <Badge className="gap-1">
                        <Sparkles className="h-3 w-3" /> Mais popular
                      </Badge>
                    </div>
                  )}
                  <h3 className="text-lg font-semibold">{p.name}</h3>
                  <div className="mt-2 text-sm text-muted-foreground">
                    {p.minutas} minutas/mês
                  </div>
                  <div className="mt-1 text-sm text-muted-foreground">
                    {p.conecta} interações JuridIA Conecta/mês
                  </div>
                  <div className="mt-5">
                    <span className="text-4xl font-bold tracking-tight">
                      R$ {finalPrice.toLocaleString("pt-BR")}
                    </span>
                    <span className="text-sm text-muted-foreground">/mês</span>
                    {billing !== "mensal" && (
                      <div className="mt-1 text-xs text-primary">
                        Economia de R$ {Math.round(p.price * DISCOUNTS[billing]).toLocaleString("pt-BR")} ({Math.round(DISCOUNTS[billing] * 100)}%)
                      </div>
                    )}
                  </div>
                  <ul className="mt-5 flex-1 space-y-2 text-sm">
                    {p.perks.map((perk) => (
                      <li key={perk} className="flex items-start gap-2">
                        <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                        <span className="text-muted-foreground">{perk}</span>
                      </li>
                    ))}
                  </ul>
                  <Button
                    className="mt-6 w-full"
                    variant={p.highlight ? "default" : "outline"}
                    onClick={() => {
                      setView("app");
                      toast({ title: `Plano ${p.name} selecionado!`, description: "Você pode testar a plataforma agora mesmo." });
                    }}
                  >
                    Escolher plano
                  </Button>
                </motion.div>
              );
            })}
          </div>
        )}

        {kind === "corporativo" && (
          <div className="mx-auto mt-12 max-w-3xl rounded-xl border border-border bg-card p-8 text-center">
            <h3 className="text-2xl font-bold">Corporativo</h3>
            <p className="mt-3 text-muted-foreground">
              Para escritórios e departamentos jurídicos com múltiplos usuários.
              Volume de minutas escalável, gestão de equipe, relatórios e
              treinamento dedicado.
            </p>
            <div className="mt-6 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Button size="lg" onClick={() => setView("app")}>Testar a plataforma</Button>
              <Button size="lg" variant="outline">Falar com vendas</Button>
            </div>
          </div>
        )}

        {kind === "enterprise" && (
          <div className="mx-auto mt-12 max-w-3xl rounded-xl border border-primary/30 bg-card p-8 text-center ring-1 ring-primary/20">
            <Badge className="mb-3"><Sparkles className="mr-1 h-3 w-3" /> Enterprise</Badge>
            <h3 className="text-2xl font-bold">Infraestrutura dedicada</h3>
            <p className="mt-3 text-muted-foreground">
              Dados 100% segregados, infraestrutura dedicada, SLA corporativo,
              on-premise opcional e auditoria personalizada. Ideal para
              Tribunais, Defensorias e Procuradorias.
            </p>
            <div className="mt-6">
              <Button size="lg">Solicitar proposta</Button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
