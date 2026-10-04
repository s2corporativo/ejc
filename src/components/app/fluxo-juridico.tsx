"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  Briefcase,
  Brain,
  Network,
  Search,
  Wand2,
  FileText,
  ShieldCheck,
  CheckCircle2,
  Circle,
  ArrowRight,
  Loader2,
  Users,
  Clock,
  DollarSign,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAppStore } from "@/lib/store";
import { toast } from "@/hooks/use-toast";

interface FluxoStep {
  id: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  tab: string;
  done: boolean;
}

const FLUXO_STEPS: FluxoStep[] = [
  { id: "cliente", label: "Cliente", icon: Users, tab: "clients", done: true },
  { id: "caso", label: "Caso", icon: Briefcase, tab: "casos", done: true },
  { id: "analise", label: "Análise IA", icon: Brain, tab: "cerebro", done: false },
  { id: "skills", label: "Skills", icon: Network, tab: "intelligence", done: false },
  { id: "pesquisa", label: "Pesquisa", icon: Search, tab: "cerebro", done: false },
  { id: "peca", label: "Peça", icon: Wand2, tab: "generator", done: false },
  { id: "revisao", label: "Revisão", icon: FileText, tab: "editor", done: false },
  { id: "citacao", label: "Citation Gate", icon: ShieldCheck, tab: "editor", done: false },
];

export function FluxoJuridico({ caseTitle, caseFacts }: { caseTitle: string; caseFacts?: string }) {
  const { setAppTab, setBrainContext, setCurrentDocId } = useAppStore();
  const [skillResults, setSkillResults] = useState<{ matches: { slug: string; name: string; matchScore: number }[]; area: string } | null>(null);
  const [routing, setRouting] = useState(false);

  // Auto-roda o Skill Router quando tem fatos
  useEffect(() => {
    if (caseFacts && caseFacts.length > 30 && !skillResults && !routing) {
      routeSkills(caseFacts);
    }
  }, [caseFacts, skillResults, routing]);

  async function routeSkills(facts: string) {
    setRouting(true);
    try {
      const res = await fetch("/api/skill-router", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ facts, caseId: "fluxo" }),
      });
      const data = await res.json();
      if (data.matches) {
        setSkillResults({ matches: data.matches, area: data.area });
      }
    } catch { /* ignore */ }
    finally { setRouting(false); }
  }

  function goToStep(tab: string, context?: string) {
    if (context) setBrainContext(context);
    setAppTab(tab as typeof tab);
  }

  function startAnalysis() {
    const ctx = `CASO: ${caseTitle}\n${caseFacts ? `FATOS: ${caseFacts}` : "Descreva os fatos do caso..."}`;
    setBrainContext(ctx);
    setAppTab("cerebro");
    toast({ title: "Fluxo iniciado", description: "Análise cerebral aberta com contexto do caso" });
  }

  return (
    <Card className="border-primary/30">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Briefcase className="h-4 w-4 text-primary" />
          Fluxo jurídico completo
          {skillResults && (
            <Badge variant="secondary" className="ml-auto gap-1 text-[10px]">
              <Network className="h-3 w-3" />
              {skillResults.matches.length} skills
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {/* Pipeline visual */}
        <div className="flex flex-wrap items-center gap-1">
          {FLUXO_STEPS.map((step, i) => (
            <div key={step.id} className="flex items-center gap-1">
              <button
                onClick={() => goToStep(step.tab)}
                className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs transition-all ${
                  step.done
                    ? "border-green-500/40 bg-green-500/5 text-green-700 dark:text-green-400"
                    : "border-border bg-card hover:border-primary/40"
                }`}
              >
                {step.done ? (
                  <CheckCircle2 className="h-3 w-3" />
                ) : (
                  <Circle className="h-3 w-3 text-muted-foreground" />
                )}
                <step.icon className="h-3 w-3" />
                <span className="hidden sm:inline">{step.label}</span>
              </button>
              {i < FLUXO_STEPS.length - 1 && (
                <ArrowRight className="h-3 w-3 text-muted-foreground/40" />
              )}
            </div>
          ))}
        </div>

        {/* Skills matched */}
        {routing && (
          <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin text-primary" />
            Identificando skills relevantes...
          </div>
        )}

        {skillResults && skillResults.matches.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-3 rounded-lg border border-primary/20 bg-primary/5 p-2.5"
          >
            <div className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-primary">
              <Network className="h-3 w-3" />
              Skills identificadas automaticamente
              <Badge variant="outline" className="ml-auto text-[10px]">{skillResults.area}</Badge>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {skillResults.matches.slice(0, 6).map((m) => (
                <Badge key={m.slug} variant="secondary" className="gap-1 text-[10px]">
                  {m.matchScore >= 0.4 ? "★" : ""}{m.name.slice(0, 30)}
                </Badge>
              ))}
            </div>
          </motion.div>
        )}

        {/* Action buttons */}
        <div className="mt-3 flex flex-wrap gap-2">
          <Button size="sm" onClick={startAnalysis} className="gap-1.5">
            <Brain className="h-3.5 w-3.5" />
            Iniciar análise
          </Button>
          {skillResults && skillResults.matches.length > 0 && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                const skillsCtx = skillResults.matches
                  .map((m) => `- ${m.name} (score: ${m.matchScore})`)
                  .join("\n");
                const ctx = `CASO: ${caseTitle}\nFATOS: ${caseFacts || ""}\nSKILLS IDENTIFICADAS:\n${skillsCtx}`;
                setBrainContext(ctx);
                setAppTab("generator");
                toast({ title: "Contexto completo enviado para produção", description: `${skillResults.matches.length} skills + fatos do caso` });
              }}
              className="gap-1.5"
            >
              <Wand2 className="h-3.5 w-3.5" />
              Gerar peça com skills
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={() => setAppTab("editor")} className="gap-1.5">
            <FileText className="h-3.5 w-3.5" />
            Revisar peça
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
