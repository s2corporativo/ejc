"use client";

import { motion } from "framer-motion";
import { useState } from "react";
import { Eye, EyeOff, Lock, ShieldAlert, Cpu, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";

const SAMPLE = `EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DE DIREITO DA 3ª VARA CÍVEL DA COMARCA DE SÃO PAULO

João Carlos da Silva, brasileiro, casado, advogado, CPF 123.456.789-09, OAB/SP 123.456, portador do RG 12.345.678-9, residente e domiciliado na Rua das Flores, 123, São Paulo - SP, CEP 01000-000, telefone (11) 99999-1234, e-mail joao.silva@email.com, por seu advogado, vem propor AÇÃO INDENIZATÓRIA em face de Maria Oliveira Santos, brasileira, solteira, CPF 987.654.321-00, residente na Rua dos Pinheiros, 456, pelos fatos a seguir, sendo o valor da causa R$ 50.000,00.`;

interface AnonResult {
  original: string;
  anonymized: string;
  markers: Record<string, string>;
  counts: Record<string, number>;
  total: number;
  detection: { type: string; count: number; sample: string }[];
}

export function Anonymization() {
  const [input, setInput] = useState(SAMPLE);
  const [result, setResult] = useState<AnonResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [showOriginal, setShowOriginal] = useState(false);

  async function run() {
    setLoading(true);
    try {
      const res = await fetch("/api/anonymize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: input }),
      });
      const data = await res.json();
      setResult(data);
    } catch {
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section id="anonimizacao" className="border-b border-border bg-secondary/30">
      <div className="container-juridia py-20">
        <div className="mx-auto max-w-2xl text-center">
          <Badge variant="secondary" className="mb-3">
            <ShieldAlert className="mr-1 h-3 w-3" /> tarja-1
          </Badge>
          <h2 className="text-3xl font-bold tracking-tight text-balance sm:text-4xl">
            Anonimização local em mão dupla
          </h2>
          <p className="mt-4 text-muted-foreground">
            Detecta dados sensíveis em documentos jurídicos brasileiros e os
            substitui por marcadores <span className="marker-chip">[NOME_0001]</span>{" "}
            <span className="marker-chip">[CPF_0001]</span> antes de qualquer
            conteúdo sair do seu computador.
          </p>
        </div>

        <div className="mt-12 grid gap-6 lg:grid-cols-2">
          {/* Input */}
          <div className="rounded-xl border border-border bg-card p-5">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="flex items-center gap-2 text-sm font-semibold">
                <Cpu className="h-4 w-4 text-primary" />
                Detecção no seu computador
              </h3>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowOriginal((v) => !v)}
              >
                {showOriginal ? (
                  <EyeOff className="mr-1 h-4 w-4" />
                ) : (
                  <Eye className="mr-1 h-4 w-4" />
                )}
                {showOriginal ? "Ocultar dados" : "Ver dados"}
              </Button>
            </div>
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              rows={12}
              className={`font-mono text-xs ${showOriginal ? "" : "blur-sm hover:blur-none transition-all"}`}
              placeholder="Cole aqui a minuta com dados sensíveis..."
            />
            <Button onClick={run} disabled={loading} className="mt-3 w-full">
              {loading ? "Anonimizando..." : "Anonimizar localmente"}
              {!loading && <ArrowRight className="ml-2 h-4 w-4" />}
            </Button>
          </div>

          {/* Output */}
          <div className="rounded-xl border border-border bg-card p-5">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
              <Lock className="h-4 w-4 text-primary" />
              O que a IA enxerga (com marcadores)
            </h3>
            <div className="min-h-[280px] rounded-md border border-border bg-secondary/50 p-3">
              {result ? (
                <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed">
                  {result.anonymized}
                </pre>
              ) : (
                <p className="py-10 text-center text-sm text-muted-foreground">
                  Clique em “Anonimizar” para ver o texto com marcadores.
                </p>
              )}
            </div>

            {result && result.total > 0 && (
              <div className="mt-4 space-y-3">
                <div className="flex flex-wrap gap-2">
                  {Object.entries(result.counts).map(([type, count]) => (
                    <Badge key={type} variant="secondary" className="font-mono">
                      {type} × {count}
                    </Badge>
                  ))}
                </div>
                <details className="rounded-md border border-border bg-background p-3">
                  <summary className="cursor-pointer text-xs font-medium">
                    Ver mapa de marcadores → valor original ({result.total} itens)
                  </summary>
                  <div className="mt-3 grid gap-1 font-mono text-[11px]">
                    {Object.entries(result.markers).map(([m, v]) => (
                      <div key={m} className="flex justify-between gap-2">
                        <span className="marker-chip">{m}</span>
                        <span className="truncate text-muted-foreground">{v}</span>
                      </div>
                    ))}
                  </div>
                </details>
              </div>
            )}
          </div>
        </div>

        {/* Three pillars */}
        <div className="mt-12 grid gap-5 sm:grid-cols-3">
          {[
            { icon: Cpu, title: "Detecção no seu computador", desc: "Reconhece nomes, endereços, CPFs, valores e outros dados sensíveis direto no português dos autos." },
            { icon: ArrowRight, title: "Mão dupla, ponta a ponta", desc: "Anonimiza antes de enviar e desanonimiza no retorno, sempre localmente." },
            { icon: Lock, title: "Marcadores, não dados", desc: "O JuridIA enxerga apenas [NOME_0001] e [ENDERECO_0001]. O conteúdo real fica local." },
          ].map((p) => (
            <motion.div
              key={p.title}
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4 }}
              className="rounded-xl border border-border bg-card p-5"
            >
              <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <p.icon className="h-4 w-4" />
              </div>
              <h4 className="font-semibold">{p.title}</h4>
              <p className="mt-1.5 text-sm text-muted-foreground">{p.desc}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
