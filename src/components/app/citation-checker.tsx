"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ShieldCheck,
  ShieldAlert,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  HelpCircle,
  Circle,
  ExternalLink,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import type { VerifyResult } from "@/lib/citation_gate";
import { toast } from "@/hooks/use-toast";

const STATUS_CONFIG = {
  verificada: {
    icon: CheckCircle2,
    label: "Verificada",
    color: "text-green-600",
    bg: "bg-green-500/10 border-green-500/30",
    badge: "border-green-500/50 text-green-600",
  },
  identificada: {
    icon: HelpCircle,
    label: "Identificada",
    color: "text-blue-600",
    bg: "bg-blue-500/10 border-blue-500/30",
    badge: "border-blue-500/50 text-blue-600",
  },
  suspeita: {
    icon: AlertTriangle,
    label: "Suspeita",
    color: "text-red-600",
    bg: "bg-red-500/10 border-red-500/30",
    badge: "border-red-500/50 text-red-600",
  },
  generica: {
    icon: Circle,
    label: "Genérica",
    color: "text-amber-600",
    bg: "bg-amber-500/10 border-amber-500/30",
    badge: "border-amber-500/50 text-amber-600",
  },
} as const;

interface CitationCheckerProps {
  content: string;
  documentId?: string;
}

export function CitationChecker({ content, documentId }: CitationCheckerProps) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<VerifyResult | null>(null);

  async function verify() {
    if (content.length < 20) {
      toast({ title: "Texto muito curto", variant: "destructive" });
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const res = await fetch("/api/citations/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: content, documentId }),
      });
      const data = await res.json();
      setResult(data);
      if (data.bloquear) {
        toast({
          title: `${data.suspeitas} citação(ões) suspeita(s)`,
          description: "Verifique antes de protocolar — possível alucinação",
          variant: "destructive",
        });
      } else if (data.total > 0) {
        toast({
          title: `${data.verificadas} de ${data.total} citações verificadas`,
          description: data.suspeitas === 0 ? "Tudo OK" : `${data.identificadas} identificadas`,
        });
      } else {
        toast({ title: "Nenhuma citação encontrada no texto" });
      }
    } catch {
      toast({ title: "Erro ao verificar citações", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            setOpen(true);
            if (!result && content.length >= 20) {
              setTimeout(verify, 200);
            }
          }}
        >
          <ShieldCheck className="mr-1.5 h-4 w-4" />
          Verificar citações
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-primary" />
            Verificação de citações
            {result && (
              <Badge
                variant="outline"
                className={`ml-auto gap-1 ${
                  result.bloquear
                    ? "border-red-500/50 text-red-600"
                    : "border-green-500/50 text-green-600"
                }`}
              >
                {result.bloquear ? (
                  <>
                    <ShieldAlert className="h-3 w-3" /> Bloqueado
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="h-3 w-3" /> Aprovado
                  </>
                )}
              </Badge>
            )}
          </DialogTitle>
        </DialogHeader>

        <div className="overflow-y-auto scrollbar-juridia max-h-[60vh]">
          {loading && (
            <div className="flex flex-col items-center justify-center gap-3 py-12">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
              <p className="text-sm text-muted-foreground">
                Verificando citações contra a base curada...
              </p>
            </div>
          )}

          {!loading && !result && (
            <div className="py-8 text-center text-sm text-muted-foreground">
              Clique em &ldquo;Verificar&rdquo; para analisar as citações do documento.
            </div>
          )}

          {!loading && result && (
            <>
              {/* Summary */}
              <div className="mb-4 grid grid-cols-4 gap-2">
                <SummaryCard label="Total" value={result.total} color="text-foreground" />
                <SummaryCard label="Verificadas" value={result.verificadas} color="text-green-600" />
                <SummaryCard label="Identificadas" value={result.identificadas} color="text-blue-600" />
                <SummaryCard label="Suspeitas" value={result.suspeitas} color="text-red-600" />
              </div>

              {/* Fail-closed warning */}
              {result.bloquear && (
                <div className="mb-4 rounded-lg border border-red-500/40 bg-red-500/5 p-3 text-sm">
                  <ShieldAlert className="mb-1 inline h-4 w-4 text-red-600" />
                  <strong className="text-red-600">Bloqueio de aprovação (fail-closed):</strong>{" "}
                  {result.suspeitas} citação(ões) não encontrada(s) na base curada.
                  Pode ser alucinação da IA ou base incompleta. Verifique a fonte
                  oficial antes de protocolar.
                </div>
              )}

              {/* Citations list */}
              {result.citations.length === 0 ? (
                <div className="py-8 text-center text-sm text-muted-foreground">
                  Nenhuma citação jurídica detectada no texto.
                </div>
              ) : (
                <div className="space-y-2">
                  {result.citations.map((c, i) => {
                    const cfg = STATUS_CONFIG[c.status];
                    const Icon = cfg.icon;
                    return (
                      <motion.div
                        key={i}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: Math.min(i * 0.05, 0.5) }}
                        className={`rounded-lg border p-3 ${cfg.bg}`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <Icon className={`h-4 w-4 ${cfg.color}`} />
                            <Badge variant="outline" className={`text-[10px] ${cfg.badge}`}>
                              {cfg.label}
                            </Badge>
                          </div>
                          <code className="text-[11px] text-muted-foreground">
                            {c.diploma} {c.numero}
                            {c.tribunal && ` ${c.tribunal}`}
                          </code>
                        </div>
                        <div className="mt-2 text-xs">
                          <span className="text-muted-foreground">Citação: </span>
                          <code className="rounded bg-secondary px-1.5 py-0.5">{c.raw}</code>
                        </div>
                        <p className="mt-1.5 text-xs text-muted-foreground">{c.reason}</p>
                        {c.source && (
                          <div className="mt-2 rounded border border-dashed border-border p-2">
                            <div className="mb-1 flex items-center justify-between">
                              <span className="text-[10px] font-medium uppercase text-muted-foreground">
                                Base curada
                              </span>
                              {!c.source.vigente && (
                                <Badge variant="outline" className="text-[10px] text-red-600 border-red-500/50">
                                  não vigente
                                </Badge>
                              )}
                            </div>
                            <p className="text-[11px] italic text-muted-foreground">
                              &ldquo;{c.source.textoTrecho.slice(0, 200)}...&rdquo;
                            </p>
                            {c.source.urlOficial && (
                              <a
                                href={c.source.urlOficial}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="mt-1.5 inline-flex items-center gap-1 text-[11px] text-primary hover:underline"
                              >
                                <ExternalLink className="h-3 w-3" />
                                Fonte oficial
                              </a>
                            )}
                          </div>
                        )}
                      </motion.div>
                    );
                  })}
                </div>
              )}

              {/* Re-verify button */}
              <Button
                variant="outline"
                size="sm"
                className="mt-4 w-full"
                onClick={verify}
                disabled={loading}
              >
                {loading ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <ShieldCheck className="mr-2 h-4 w-4" />
                )}
                Verificar novamente
              </Button>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function SummaryCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="rounded-lg border border-border p-2.5 text-center">
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
      <div className="text-[10px] text-muted-foreground">{label}</div>
    </div>
  );
}
