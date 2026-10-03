"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Wand2,
  Loader2,
  Check,
  X,
  Plus,
  Minus,
  RefreshCw,
  FileDiff,
  Lightbulb,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAppStore } from "@/lib/store";
import { toast } from "@/hooks/use-toast";

interface MoldeChange {
  operation: "replace" | "add" | "remove";
  anchor: string;
  replacement?: string | null;
  reason: string;
}

interface MoldeProps {
  baseContent: string;
  templateName: string;
  onApply: (newContent: string) => void;
}

export function MoldeMode({ baseContent, templateName, onApply }: MoldeProps) {
  const [instruction, setInstruction] = useState("");
  const [loading, setLoading] = useState(false);
  const [changes, setChanges] = useState<(MoldeChange & { id: string; status: "pending" | "accepted" | "rejected" })[]>([]);

  async function generateChanges() {
    if (!instruction.trim()) {
      toast({ title: "Digite uma instrução", variant: "destructive" });
      return;
    }
    if (baseContent.length < 50) {
      toast({ title: "Documento-base muito curto", variant: "destructive" });
      return;
    }
    setLoading(true);
    setChanges([]);
    try {
      const res = await fetch("/api/molde", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          baseDocument: baseContent,
          instruction,
          templateName,
        }),
      });
      const data = await res.json();
      if (data.error) {
        toast({ title: data.error, variant: "destructive" });
      } else if (data.changes?.length > 0) {
        const withIds = data.changes.map((c: MoldeChange, i: number) => ({
          ...c,
          id: `change-${Date.now()}-${i}`,
          status: "pending" as const,
        }));
        setChanges(withIds);
        toast({ title: `${withIds.length} alterações propostas`, description: "Revise e aceite/rejeite cada uma" });
      } else {
        toast({ title: "Nenhuma alteração proposta", description: "A IA não identificou mudanças necessárias." });
      }
    } catch {
      toast({ title: "Erro no Modo Molde", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  }

  function setStatus(id: string, status: "accepted" | "rejected") {
    setChanges((prev) => prev.map((c) => (c.id === id ? { ...c, status } : c)));
  }

  function applyAccepted() {
    const accepted = changes.filter((c) => c.status === "accepted");
    if (accepted.length === 0) {
      toast({ title: "Nenhuma alteração aceita", variant: "destructive" });
      return;
    }
    let newContent = baseContent;
    for (const c of accepted) {
      if (c.operation === "replace" && c.replacement) {
        newContent = newContent.split(c.anchor).join(c.replacement);
      } else if (c.operation === "remove") {
        newContent = newContent.split(c.anchor).join("");
      } else if (c.operation === "add" && c.replacement) {
        // adiciona após o anchor
        const idx = newContent.indexOf(c.anchor);
        if (idx >= 0) {
          const end = idx + c.anchor.length;
          newContent = newContent.slice(0, end) + "\n" + c.replacement + newContent.slice(end);
        } else {
          newContent += "\n" + c.replacement;
        }
      }
    }
    onApply(newContent);
    setChanges([]);
    setInstruction("");
    toast({
      title: `${accepted.length} alterações aplicadas`,
      description: "Documento-base atualizado. Revise no editor.",
    });
  }

  const acceptedCount = changes.filter((c) => c.status === "accepted").length;

  return (
    <div className="space-y-4">
      {/* Instruction input */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm">
            <Wand2 className="h-4 w-4 text-primary" />
            Modo Molde — alterações estruturadas
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="molde-instruction" className="text-xs">
              O que alterar no documento?
            </Label>
            <Textarea
              id="molde-instruction"
              rows={3}
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder="Ex: incluir pedido de tutela de urgência com base no art. 300 do CPC"
            />
          </div>
          <div className="flex gap-2">
            <Button onClick={generateChanges} disabled={loading || !instruction.trim()} size="sm">
              {loading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Gerando alterações...
                </>
              ) : (
                <>
                  <FileDiff className="mr-2 h-4 w-4" />
                  Propor alterações
                </>
              )}
            </Button>
          </div>
          <div className="rounded-md border border-dashed border-primary/40 bg-primary/5 p-2.5 text-xs text-muted-foreground">
            <Lightbulb className="mb-1 inline h-3.5 w-3.5 text-primary" />{" "}
            <strong>Modo Molde:</strong> a IA propõe alterações pontuais (substituir,
            adicionar, remover) sobre o documento-base, em vez de reescrevê-lo. Você
            aceita ou rejeita cada mudança individualmente.
          </div>
        </CardContent>
      </Card>

      {/* Proposed changes */}
      <AnimatePresence>
        {changes.length > 0 && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="space-y-3"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">
                {changes.length} alterações propostas
              </h3>
              <Badge variant="secondary" className="gap-1">
                <Check className="h-3 w-3" /> {acceptedCount} aceitas
              </Badge>
            </div>

            <div className="space-y-3">
              {changes.map((c, i) => (
                <motion.div
                  key={c.id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.05 }}
                  className={`rounded-lg border p-3 transition-all ${
                    c.status === "accepted"
                      ? "border-primary/50 bg-primary/5"
                      : c.status === "rejected"
                      ? "border-destructive/30 bg-destructive/5 opacity-60"
                      : "border-border bg-card"
                  }`}
                >
                  <div className="mb-2 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Badge
                        variant="outline"
                        className={`gap-1 text-[10px] ${
                          c.operation === "replace"
                            ? "text-blue-600"
                            : c.operation === "add"
                            ? "text-green-600"
                            : "text-red-600"
                        }`}
                      >
                        {c.operation === "replace" && <RefreshCw className="h-2.5 w-2.5" />}
                        {c.operation === "add" && <Plus className="h-2.5 w-2.5" />}
                        {c.operation === "remove" && <Minus className="h-2.5 w-2.5" />}
                        {c.operation === "replace" ? "substituir" : c.operation === "add" ? "adicionar" : "remover"}
                      </Badge>
                      <span className="text-[10px] text-muted-foreground">#{i + 1}</span>
                    </div>
                    <div className="flex gap-1">
                      <Button
                        size="sm"
                        variant={c.status === "accepted" ? "default" : "outline"}
                        className="h-7 px-2"
                        onClick={() => setStatus(c.id, "accepted")}
                        disabled={c.status === "accepted"}
                      >
                        <Check className="h-3 w-3" />
                      </Button>
                      <Button
                        size="sm"
                        variant={c.status === "rejected" ? "destructive" : "outline"}
                        className="h-7 px-2"
                        onClick={() => setStatus(c.id, "rejected")}
                        disabled={c.status === "rejected"}
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>

                  {/* Anchor (trecho original) */}
                  <div className="mb-2">
                    <div className="mb-1 text-[10px] font-medium uppercase text-muted-foreground">
                      {c.operation === "add" ? "Inserir após" : "Trecho do documento"}
                    </div>
                    <pre className="max-h-24 overflow-y-auto whitespace-pre-wrap rounded border border-border bg-secondary/50 p-2 font-mono text-[11px] scrollbar-juridia">
                      {c.anchor}
                    </pre>
                  </div>

                  {/* Replacement */}
                  {c.operation !== "remove" && c.replacement && (
                    <div className="mb-2">
                      <div className="mb-1 text-[10px] font-medium uppercase text-primary">
                        {c.operation === "replace" ? "Substituir por" : "Adicionar"}
                      </div>
                      <pre className="max-h-32 overflow-y-auto whitespace-pre-wrap rounded border border-primary/30 bg-primary/5 p-2 font-mono text-[11px] scrollbar-juridia">
                        {c.replacement}
                      </pre>
                    </div>
                  )}

                  {/* Reason */}
                  {c.reason && (
                    <div className="text-[10px] text-muted-foreground">
                      <strong>Motivo:</strong> {c.reason}
                    </div>
                  )}
                </motion.div>
              ))}
            </div>

            {acceptedCount > 0 && (
              <Button onClick={applyAccepted} className="w-full" size="sm">
                <Check className="mr-2 h-4 w-4" />
                Aplicar {acceptedCount} alteração{acceptedCount > 1 ? "ões" : ""} ao documento
              </Button>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
