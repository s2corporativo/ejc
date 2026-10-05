"use client";

import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  Loader2,
  FileText,
  Calendar,
  Gavel,
  Building2,
  User,
  Scale,
  AlertTriangle,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { toast } from "@/hooks/use-toast";

interface Processo {
  cnj: string;
  numero: string;
  classe: string;
  assunto: string;
  orgaoJulgador: string;
  orgao: string;
  grau: string;
  dataDistribuicao: string;
  valorCausa: string;
  situacao: string;
  partes: { tipo: string; nome: string; advogado?: string }[];
  movimentos: { data: string; descricao: string; tipo?: string }[];
}

// ── Máscara CNJ: NNNNNNN-DD.AAAA.J.TR.OOOO ──────────────────────────────────
function formatarCnj(input: string): string {
  const digits = input.replace(/\D/g, "").slice(0, 20);
  if (digits.length === 0) return "";
  let s = digits;
  // Aplica: 7 + 2 + 4 + 1 + 2 + 4 = 20 dígitos
  let out = "";
  if (s.length > 0) out = s.slice(0, 7);
  if (s.length > 7) out += "-" + s.slice(7, 9);
  if (s.length > 9) out += "." + s.slice(9, 13);
  if (s.length > 13) out += "." + s.slice(13, 14);
  if (s.length > 14) out += "." + s.slice(14, 16);
  if (s.length > 16) out += "." + s.slice(16, 20);
  return out;
}

// ── Mocks de processos para demonstração ────────────────────────────────────
function mockProcesso(cnj: string): Processo {
  // Deriva um mock determinístico a partir do CNJ (hash leve)
  const seed = cnj.split("").reduce((s, c) => s + c.charCodeAt(0), 0);
  const classes = ["Procedimento Comum Cível", "Cumprimento de Sentença", "Cumprimento Provisório de Sentença", "Embargos de Declaração", "Ação Indenizatória"];
  const assuntos = ["Indenização por Dano Moral", "Obrigação de Fazer / Não Fazer", "Cobrança", "Prestação de Serviços", "Contratos"];
  const orgaos = ["1ª Vara Cível", "2ª Vara Cível", "Vara de Fazenda Pública", "Juizado Especial Cível", "Câmara Cível"];
  const nomes = ["João Silva", "Maria Santos", "Construtora ABC Ltda.", "Empresa XYZ S.A.", "Pedro Alves"];
  const advs = ["Ana Souza OAB/SP 123.456", "Bruno Lima OAB/RJ 234.567"];
  const classe = classes[seed % classes.length];
  const assunto = assuntos[(seed * 3) % assuntos.length];
  const orgao = orgaos[(seed * 7) % orgaos.length];
  const autor = nomes[seed % nomes.length];
  const reu = nomes[(seed * 5 + 1) % nomes.length];
  const adv = advs[seed % advs.length];

  const dataDistribuicao = new Date(2024, (seed % 12), ((seed % 28) + 1)).toISOString().slice(0, 10);
  const valorCausa = (seed * 100 + 1000).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

  const movs: { data: string; descricao: string; tipo?: string }[] = [
    { data: dataDistribuicao, descricao: "Petição inicial protocolada", tipo: "petição" },
    { data: addDays(dataDistribuicao, 5), descricao: "Despacho: designada audiência de conciliação", tipo: "despacho" },
    { data: addDays(dataDistribuicao, 15), descricao: "Audiência de conciliação realizada — sem acordo", tipo: "audiência" },
    { data: addDays(dataDistribuicao, 22), descricao: "Contestação protocolada pelo réu", tipo: "petição" },
    { data: addDays(dataDistribuicao, 30), descricao: "Réplica apresentada pelo autor", tipo: "petição" },
    { data: addDays(dataDistribuicao, 50), descricao: "Audiência de instrução e julgamento designada", tipo: "despacho" },
    { data: addDays(dataDistribuicao, 75), descricao: "Audiência de instrução realizada — oitiva de testemunhas", tipo: "audiência" },
    { data: addDays(dataDistribuicao, 90), descricao: "Memórias finais apresentadas", tipo: "petição" },
    { data: addDays(dataDistribuicao, 120), descricao: "Sentença: procedência parcial dos pedidos", tipo: "sentença" },
  ];

  return {
    cnj,
    numero: cnj,
    classe,
    assunto,
    orgaoJulgador: orgao,
    orgao: "TJSP — Tribunal de Justiça de São Paulo",
    grau: "1º Grau",
    dataDistribuicao,
    valorCausa,
    situacao: "Em grau de recurso",
    partes: [
      { tipo: "Autor", nome: autor, advogado: adv },
      { tipo: "Réu", nome: reu, advogado: advs[(seed + 1) % advs.length] },
    ],
    movimentos: movs,
  };
}

function addDays(dateStr: string, days: number): string {
  const d = new Date(dateStr);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export function DataJudBusca() {
  const [cnj, setCnj] = useState("");
  const [loading, setLoading] = useState(false);
  const [processo, setProcesso] = useState<Processo | null>(null);

  function buscar() {
    const digits = cnj.replace(/\D/g, "");
    if (digits.length !== 20) {
      toast({ title: "CNJ inválido", description: "Formato: NNNNNNN-DD.AAAA.J.TR.OOOO (20 dígitos)", variant: "destructive" });
      return;
    }
    setLoading(true);
    setProcesso(null);
    // Simula latência de consulta pública
    setTimeout(() => {
      setProcesso(mockProcesso(cnj));
      setLoading(false);
      toast({ title: "Processo encontrado", description: cnj });
    }, 800);
  }

  function preencherExemplo() {
    setCnj(formatarCnj("00000012345678901234"));
  }

  return (
    <div className="container-juridia py-8">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Search className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">DataJud — Busca de processos</h1>
            <p className="text-sm text-muted-foreground">Consulta pública do CNJ com máscara automática e timeline de movimentações.</p>
          </div>
        </div>
      </motion.div>

      <Card className="mb-6">
        <CardContent className="p-4">
          <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
            <div>
              <Label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Número CNJ</Label>
              <Input
                value={cnj}
                onChange={(e) => setCnj(formatarCnj(e.target.value))}
                onKeyDown={(e) => { if (e.key === "Enter") buscar(); }}
                placeholder="0000000-00.0000.0.00.0000"
                className="font-mono"
                maxLength={25}
              />
            </div>
            <div className="flex gap-2">
              <Button onClick={buscar} disabled={loading || cnj.replace(/\D/g, "").length !== 20}>
                {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Search className="mr-2 h-4 w-4" />}
                {loading ? "Buscando..." : "Buscar"}
              </Button>
              <Button variant="outline" onClick={preencherExemplo}>Exemplo</Button>
            </div>
          </div>
          <p className="mt-2 text-[10px] text-muted-foreground">
            ⚠ DataJud/TPU via API pública REST ainda não liberada localmente — demonstração usa dados simulados. Em produção, consulte o endpoint oficial do CNJ.
          </p>
        </CardContent>
      </Card>

      <AnimatePresence mode="wait">
        {loading ? (
          <motion.div key="loading" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex flex-col items-center justify-center gap-2 py-16">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <p className="text-sm text-muted-foreground">Consultando base pública do CNJ...</p>
          </motion.div>
        ) : processo ? (
          <motion.div key="result" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} className="grid gap-6 lg:grid-cols-3">
            {/* Card principal */}
            <Card className="lg:col-span-2">
              <CardHeader>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <FileText className="h-4 w-4 text-primary" /> {processo.classe}
                    </CardTitle>
                    <p className="mt-1 font-mono text-xs text-muted-foreground">{processo.numero}</p>
                  </div>
                  <Badge variant="outline" className={`text-[10px] ${processo.situacao.includes("recur") ? "border-amber-500/40 text-amber-600" : "border-emerald-500/40 text-emerald-600"}`}>
                    {processo.situacao}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  <Field icon={Scale} label="Assunto" value={processo.assunto} />
                  <Field icon={Building2} label="Órgão julgador" value={processo.orgaoJulgador} />
                  <Field icon={Gavel} label="Grau" value={processo.grau} />
                  <Field icon={Calendar} label="Distribuição" value={new Date(processo.dataDistribuicao).toLocaleDateString("pt-BR")} />
                  <Field icon={FileText} label="Valor da causa" value={processo.valorCausa} />
                  <Field icon={Building2} label="Tribunal" value={processo.orgao} />
                </div>

                {/* Partes */}
                <div className="mt-4">
                  <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Partes</div>
                  <div className="space-y-1.5">
                    {processo.partes.map((p, i) => (
                      <div key={i} className="flex items-center gap-2 rounded border border-border p-2 text-xs">
                        <Badge variant="secondary" className="text-[10px]">{p.tipo}</Badge>
                        <User className="h-3 w-3 text-muted-foreground" />
                        <span className="flex-1 font-medium">{p.nome}</span>
                        {p.advogado && <span className="text-[10px] text-muted-foreground">{p.advogado}</span>}
                      </div>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Timeline */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Calendar className="h-4 w-4 text-primary" /> Movimentações
                  <Badge variant="secondary" className="ml-auto text-[10px]">{processo.movimentos.length}</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="relative max-h-[70vh] overflow-y-auto pl-6 scrollbar-juridia">
                  <div className="absolute left-2 top-2 bottom-2 w-px bg-border" />
                  <div className="space-y-3">
                    {processo.movimentos.map((m, i) => (
                      <motion.div
                        key={i}
                        initial={{ opacity: 0, x: -8 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: Math.min(i * 0.05, 0.5) }}
                        className="relative"
                      >
                        <div className="absolute -left-5 top-1.5 h-2 w-2 rounded-full bg-primary ring-4 ring-background" />
                        <div className="rounded border border-border p-2">
                          <div className="flex items-center gap-2 text-[10px]">
                            <span className="font-mono text-primary">{new Date(m.data).toLocaleDateString("pt-BR")}</span>
                            {m.tipo && <Badge variant="outline" className="text-[9px]">{m.tipo}</Badge>}
                          </div>
                          <div className="mt-0.5 text-xs">{m.descricao}</div>
                        </div>
                      </motion.div>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        ) : (
          <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex flex-col items-center justify-center gap-3 py-16 text-center">
            <Search className="h-12 w-12 text-muted-foreground/40" />
            <div>
              <h3 className="font-semibold">Digite um número CNJ</h3>
              <p className="mt-1 text-sm text-muted-foreground">Use o botão <strong>Exemplo</strong> para preencher automaticamente.</p>
            </div>
            <div className="rounded-lg border border-dashed border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-700 dark:text-amber-400">
              <AlertTriangle className="mr-1 inline h-3.5 w-3.5" />
              Modo demonstração: dados simulados.
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Field({ icon: Icon, label, value }: { icon: React.ComponentType<{ className?: string }>; label: string; value: string }) {
  return (
    <div className="rounded border border-border p-2">
      <div className="flex items-center gap-1 text-[9px] uppercase tracking-wider text-muted-foreground">
        <Icon className="h-2.5 w-2.5" /> {label}
      </div>
      <div className="mt-1 text-xs font-medium">{value}</div>
    </div>
  );
}
