"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Calculator,
  CalendarClock,
  TrendingUp,
  Percent,
  Hourglass,
  ShieldCheck,
  DollarSign,
  Filter,
  EyeOff,
  ListChecks,
  AlertTriangle,
  CheckCircle2,
  Copy,
  Loader2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { toast } from "@/hooks/use-toast";

type ToolId =
  | "prazo"
  | "correcao"
  | "juros"
  | "prescricao"
  | "salvaguardas"
  | "valor-causa"
  | "triagem"
  | "vedacao-surpresa"
  | "checklist-julgador";

interface ToolDef {
  id: ToolId;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  description: string;
  color: string;
}

const TOOLS: ToolDef[] = [
  { id: "prazo", label: "Prazo processual", icon: CalendarClock, description: "Contagem em dias úteis/corridos (art. 219/224 CPC)", color: "text-emerald-600" },
  { id: "correcao", label: "Correção monetária", icon: TrendingUp, description: "IPCA/INPC — fator acumulado", color: "text-amber-600" },
  { id: "juros", label: "Juros de mora", icon: Percent, description: "CC art. 406 / STJ Súmula 482 / CLT", color: "text-cyan-600" },
  { id: "prescricao", label: "Prescrição", icon: Hourglass, description: "CC art. 205/206, CDC art. 27, CLT art. 11", color: "text-rose-600" },
  { id: "salvaguardas", label: "Salvaguardas", icon: ShieldCheck, description: "Cláusulas de proteção contratual", color: "text-purple-600" },
  { id: "valor-causa", label: "Valor da causa", icon: DollarSign, description: "Verificação do art. 291-294 CPC", color: "text-orange-600" },
  { id: "triagem", label: "Triagem de risco", icon: Filter, description: "Classifica caso por prioridade e área", color: "text-emerald-600" },
  { id: "vedacao-surpresa", label: "Vedação à decisão surpresa", icon: EyeOff, description: "Art. 10 do CPC — contraditório prévio", color: "text-amber-600" },
  { id: "checklist-julgador", label: "Checklist do julgador", icon: ListChecks, description: "Admissibilidade + mérito (pré-protocolo)", color: "text-cyan-600" },
];

interface ResultState {
  tool: ToolId;
  payload: Record<string, unknown>;
  observacoes?: string[];
}

const fmtMoeda = (n: number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(n);

export function CalculadoraJuridica() {
  const [activeTool, setActiveTool] = useState<ToolId>("prazo");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ResultState | null>(null);

  // ── formulários por ferramenta ──────────────────────────────────────────────
  const [prazoForm, setPrazoForm] = useState({ marcoInicial: "", prazoDias: "15", tipoContagem: "uteis" });
  const [correcaoForm, setCorrecaoForm] = useState({ valorOriginal: "", fatorAcumulado: "1.5", indice: "IPCA" });
  const [jurosForm, setJurosForm] = useState({ valorPrincipal: "", meses: "12", taxaMensal: "0.01", base: "cc_art_406" });
  const [prescForm, setPrescForm] = useState({ dataFato: "", dataAjuizamento: "", area: "civil" });
  const [valorCausaForm, setValorCausaForm] = useState({ valor: "", pedidos: "", area: "civil" });
  const [triagemForm, setTriagemForm] = useState({ fatos: "", area: "civil", valorCausa: "", provas: "" });
  const [vedacaoForm, setVedacaoForm] = useState({ decisao: "", partes: "", fundamentos: "" });
  const [salvaguardasForm, setSalvaguardasForm] = useState({ contrato: "", area: "consumer" });

  async function calcular() {
    setLoading(true);
    setResult(null);
    try {
      if (activeTool === "prazo") {
        if (!prazoForm.marcoInicial || !prazoForm.prazoDias) throw new Error("Marco inicial e prazo em dias obrigatórios");
        const res = await fetch("/api/superior/calculate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ type: "deadline", marcoInicial: prazoForm.marcoInicial, prazoDias: Number(prazoForm.prazoDias), tipoContagem: prazoForm.tipoContagem }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Erro");
        setResult({ tool: "prazo", payload: data, observacoes: data.observacoes });
      } else if (activeTool === "correcao") {
        const v = Number(correcaoForm.valorOriginal);
        const f = Number(correcaoForm.fatorAcumulado);
        if (!v || !f) throw new Error("Valor original e fator obrigatórios");
        const res = await fetch("/api/superior/calculate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ type: "correction", valorOriginal: v, fatorAcumulado: f, indice: correcaoForm.indice }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Erro");
        setResult({ tool: "correcao", payload: data, observacoes: data.observacoes });
      } else if (activeTool === "juros") {
        const v = Number(jurosForm.valorPrincipal);
        const m = Number(jurosForm.meses);
        if (!v || !m) throw new Error("Valor principal e meses obrigatórios");
        const res = await fetch("/api/superior/calculate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ type: "interest", valorPrincipal: v, meses: m, taxaMensal: Number(jurosForm.taxaMensal), base: jurosForm.base }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Erro");
        setResult({ tool: "juros", payload: data });
      } else if (activeTool === "prescricao") {
        if (!prescForm.dataFato || !prescForm.dataAjuizamento) throw new Error("Datas obrigatórias");
        const res = await fetch("/api/superior/calculate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ type: "prescription", dataFato: prescForm.dataFato, dataajuizamento: prescForm.dataAjuizamento, area: prescForm.area }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Erro");
        setResult({ tool: "prescricao", payload: data, observacoes: data.observacoes });
      } else if (activeTool === "salvaguardas") {
        const obs = buildSalvaguardas(salvaguardasForm.contrato, salvaguardasForm.area);
        setResult({ tool: "salvaguardas", payload: { area: salvaguardasForm.area, ...obs.payload }, observacoes: obs.observacoes });
      } else if (activeTool === "valor-causa") {
        const v = Number(valorCausaForm.valor.replace(/\./g, "").replace(",", "."));
        const obs = checkValorCausa(v, valorCausaForm.pedidos, valorCausaForm.area);
        setResult({ tool: "valor-causa", payload: { valor: v, area: valorCausaForm.area, ...obs.payload }, observacoes: obs.observacoes });
      } else if (activeTool === "triagem") {
        const obs = triagemRisco(triagemForm);
        setResult({ tool: "triagem", payload: { ...obs.payload, area: triagemForm.area }, observacoes: obs.observacoes });
      } else if (activeTool === "vedacao-surpresa") {
        const obs = checkVedacaoSurpresa(vedacaoForm);
        setResult({ tool: "vedacao-surpresa", payload: obs.payload, observacoes: obs.observacoes });
      } else if (activeTool === "checklist-julgador") {
        const obs = checklistJulgador(triagemForm);
        setResult({ tool: "checklist-julgador", payload: obs.payload, observacoes: obs.observacoes });
      }
    } catch (e) {
      toast({ title: "Erro", description: e instanceof Error ? e.message : "Erro ao calcular", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  }

  function copyResult() {
    if (!result) return;
    navigator.clipboard.writeText(JSON.stringify(result.payload, null, 2));
    toast({ title: "Resultado copiado" });
  }

  return (
    <div className="container-juridia py-8">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Calculator className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Calculadora jurídica</h1>
            <p className="text-sm text-muted-foreground">9 ferramentas determinísticas — sem delegar aritmética à IA. Base normativa auditável.</p>
          </div>
        </div>
      </motion.div>

      {/* Toolbar de ferramentas */}
      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-3">
        {TOOLS.map((t) => (
          <button
            key={t.id}
            onClick={() => { setActiveTool(t.id); setResult(null); }}
            className={`group flex items-center gap-3 rounded-lg border border-border bg-card p-3 text-left transition-all hover:border-primary/40 hover:shadow-md ${activeTool === t.id ? "ring-1 ring-primary/40 border-primary/40 bg-primary/5" : ""}`}
          >
            <div className={`flex h-9 w-9 items-center justify-center rounded-lg bg-secondary ${t.color} group-hover:bg-primary/10`}>
              <t.icon className="h-4 w-4" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold">{t.label}</div>
              <div className="truncate text-[10px] text-muted-foreground">{t.description}</div>
            </div>
          </button>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Coluna esquerda — formulário */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              {(() => {
                const def = TOOLS.find((t) => t.id === activeTool)!;
                return <><def.icon className={`h-4 w-4 ${def.color}`} /> {def.label}</>;
              })()}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Tabs value={activeTool} onValueChange={(v) => { setActiveTool(v as ToolId); setResult(null); }}>
              <TabsList className="hidden">
                <TabsTrigger value="prazo">Prazo</TabsTrigger>
              </TabsList>

              <TabsContent value="prazo" className="space-y-3 mt-0">
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Marco inicial</Label>
                    <Input type="date" value={prazoForm.marcoInicial} onChange={(e) => setPrazoForm(s => ({ ...s, marcoInicial: e.target.value }))} />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Prazo (dias)</Label>
                    <Input type="number" value={prazoForm.prazoDias} onChange={(e) => setPrazoForm(s => ({ ...s, prazoDias: e.target.value }))} />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Tipo de contagem</Label>
                  <Select value={prazoForm.tipoContagem} onValueChange={(v) => setPrazoForm(s => ({ ...s, tipoContagem: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="uteis">Dias úteis (exclui sáb/dom)</SelectItem>
                      <SelectItem value="corridos">Dias corridos</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </TabsContent>

              <TabsContent value="correcao" className="space-y-3 mt-0">
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Valor original (R$)</Label>
                    <Input type="number" step="0.01" value={correcaoForm.valorOriginal} onChange={(e) => setCorrecaoForm(s => ({ ...s, valorOriginal: e.target.value }))} placeholder="10000.00" />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Fator acumulado</Label>
                    <Input type="number" step="0.0001" value={correcaoForm.fatorAcumulado} onChange={(e) => setCorrecaoForm(s => ({ ...s, fatorAcumulado: e.target.value }))} placeholder="1.5000" />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Índice</Label>
                  <Select value={correcaoForm.indice} onValueChange={(v) => setCorrecaoForm(s => ({ ...s, indice: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="IPCA">IPCA (IBGE)</SelectItem>
                      <SelectItem value="INPC">INPC (IBGE)</SelectItem>
                      <SelectItem value="IGP-M">IGP-M (FGV)</SelectItem>
                      <SelectItem value="TR">TR (BCB)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </TabsContent>

              <TabsContent value="juros" className="space-y-3 mt-0">
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Valor principal (R$)</Label>
                    <Input type="number" step="0.01" value={jurosForm.valorPrincipal} onChange={(e) => setJurosForm(s => ({ ...s, valorPrincipal: e.target.value }))} placeholder="10000.00" />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Meses</Label>
                    <Input type="number" value={jurosForm.meses} onChange={(e) => setJurosForm(s => ({ ...s, meses: e.target.value }))} placeholder="12" />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Taxa mensal (decimal)</Label>
                    <Input type="number" step="0.001" value={jurosForm.taxaMensal} onChange={(e) => setJurosForm(s => ({ ...s, taxaMensal: e.target.value }))} placeholder="0.01 = 1%" />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Base normativa</Label>
                    <Select value={jurosForm.base} onValueChange={(v) => setJurosForm(s => ({ ...s, base: v }))}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="cc_art_406">CC art. 406 (1% a.m.)</SelectItem>
                        <SelectItem value="stj_482">STJ Súmula 482 (0,5% a.m.)</SelectItem>
                        <SelectItem value="clt">CLT (1% a.m.)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="prescricao" className="space-y-3 mt-0">
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Data do fato</Label>
                    <Input type="date" value={prescForm.dataFato} onChange={(e) => setPrescForm(s => ({ ...s, dataFato: e.target.value }))} />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Data do ajuizamento</Label>
                    <Input type="date" value={prescForm.dataAjuizamento} onChange={(e) => setPrescForm(s => ({ ...s, dataAjuizamento: e.target.value }))} />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Área</Label>
                  <Select value={prescForm.area} onValueChange={(v) => setPrescForm(s => ({ ...s, area: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="civil">Civil (10 anos)</SelectItem>
                      <SelectItem value="consumer">Consumidor (5 anos)</SelectItem>
                      <SelectItem value="trabalhista">Trabalhista (5+2 anos)</SelectItem>
                      <SelectItem value="tributario">Tributário (5 anos)</SelectItem>
                      <SelectItem value="penal">Penal (varia)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </TabsContent>

              <TabsContent value="salvaguardas" className="space-y-3 mt-0">
                <div className="space-y-1.5">
                  <Label className="text-xs">Contrato/cláusula (texto)</Label>
                  <Textarea rows={4} value={salvaguardasForm.contrato} onChange={(e) => setSalvaguardasForm(s => ({ ...s, contrato: e.target.value }))} placeholder="Cole aqui o texto do contrato ou cláusula..." />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Área</Label>
                  <Select value={salvaguardasForm.area} onValueChange={(v) => setSalvaguardasForm(s => ({ ...s, area: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="consumer">Consumidor (CDC)</SelectItem>
                      <SelectItem value="civil">Civil (CC)</SelectItem>
                      <SelectItem value="empresarial">Empresarial</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </TabsContent>

              <TabsContent value="valor-causa" className="space-y-3 mt-0">
                <div className="space-y-1.5">
                  <Label className="text-xs">Valor da causa (R$)</Label>
                  <Input value={valorCausaForm.valor} onChange={(e) => setValorCausaForm(s => ({ ...s, valor: e.target.value }))} placeholder="10.000,00" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Pedidos (separe por vírgula)</Label>
                  <Textarea rows={3} value={valorCausaForm.pedidos} onChange={(e) => setValorCausaForm(s => ({ ...s, pedidos: e.target.value }))} placeholder="Indenização, tutela de urgência, etc." />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Área</Label>
                  <Select value={valorCausaForm.area} onValueChange={(v) => setValorCausaForm(s => ({ ...s, area: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="civil">Cível</SelectItem>
                      <SelectItem value="trabalhista">Trabalhista</SelectItem>
                      <SelectItem value="consumer">Consumidor</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </TabsContent>

              <TabsContent value="triagem" className="space-y-3 mt-0">
                <div className="space-y-1.5">
                  <Label className="text-xs">Fatos do caso</Label>
                  <Textarea rows={4} value={triagemForm.fatos} onChange={(e) => setTriagemForm(s => ({ ...s, fatos: e.target.value }))} placeholder="Resumo dos fatos..." />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Área</Label>
                    <Select value={triagemForm.area} onValueChange={(v) => setTriagemForm(s => ({ ...s, area: v }))}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="civil">Cível</SelectItem>
                        <SelectItem value="trabalhista">Trabalhista</SelectItem>
                        <SelectItem value="consumer">Consumidor</SelectItem>
                        <SelectItem value="tributario">Tributário</SelectItem>
                        <SelectItem value="penal">Penal</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Valor da causa</Label>
                    <Input value={triagemForm.valorCausa} onChange={(e) => setTriagemForm(s => ({ ...s, valorCausa: e.target.value }))} placeholder="R$ 0,00" />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Provas disponíveis</Label>
                  <Textarea rows={2} value={triagemForm.provas} onChange={(e) => setTriagemForm(s => ({ ...s, provas: e.target.value }))} placeholder="documental, testemunhal, pericial..." />
                </div>
              </TabsContent>

              <TabsContent value="vedacao-surpresa" className="space-y-3 mt-0">
                <div className="space-y-1.5">
                  <Label className="text-xs">Decisão pretendida</Label>
                  <Textarea rows={3} value={vedacaoForm.decisao} onChange={(e) => setVedacaoForm(s => ({ ...s, decisao: e.target.value }))} placeholder="Ex: extinção do processo sem resolução do mérito..." />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Partes ouvidas?</Label>
                  <Input value={vedacaoForm.partes} onChange={(e) => setVedacaoForm(s => ({ ...s, partes: e.target.value }))} placeholder="sim/não/parcial" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Fundamentos invocados</Label>
                  <Textarea rows={2} value={vedacaoForm.fundamentos} onChange={(e) => setVedacaoForm(s => ({ ...s, fundamentos: e.target.value }))} placeholder="art. 485, IV CPC..." />
                </div>
              </TabsContent>

              <TabsContent value="checklist-julgador" className="space-y-3 mt-0">
                <div className="space-y-1.5">
                  <Label className="text-xs">Fatos do caso (para análise de admissibilidade)</Label>
                  <Textarea rows={4} value={triagemForm.fatos} onChange={(e) => setTriagemForm(s => ({ ...s, fatos: e.target.value }))} placeholder="Resumo dos fatos..." />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Área</Label>
                    <Select value={triagemForm.area} onValueChange={(v) => setTriagemForm(s => ({ ...s, area: v }))}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="civil">Cível</SelectItem>
                        <SelectItem value="trabalhista">Trabalhista</SelectItem>
                        <SelectItem value="consumer">Consumidor</SelectItem>
                        <SelectItem value="tributario">Tributário</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Valor da causa</Label>
                    <Input value={triagemForm.valorCausa} onChange={(e) => setTriagemForm(s => ({ ...s, valorCausa: e.target.value }))} placeholder="R$ 0,00" />
                  </div>
                </div>
              </TabsContent>

              <Button onClick={calcular} disabled={loading} className="mt-2 w-full">
                {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Calculator className="mr-2 h-4 w-4" />}
                Calcular
              </Button>
            </Tabs>
          </CardContent>
        </Card>

        {/* Coluna direita — resultado */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2 text-base">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" /> Resultado determinístico
              </CardTitle>
              {result && (
                <Button size="sm" variant="ghost" onClick={copyResult}>
                  <Copy className="mr-1 h-3 w-3" /> Copiar
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent>
            <AnimatePresence mode="wait">
              {result ? (
                <motion.div
                  key={result.tool + JSON.stringify(result.payload)}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  className="space-y-4"
                >
                  <ResultRenderer result={result} />
                </motion.div>
              ) : (
                <motion.div
                  key="empty"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="flex flex-col items-center justify-center gap-2 py-12 text-center"
                >
                  <Calculator className="h-10 w-10 text-muted-foreground/40" />
                  <p className="text-sm text-muted-foreground">Preencha o formulário e clique em <strong>Calcular</strong>.</p>
                </motion.div>
              )}
            </AnimatePresence>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function ResultRenderer({ result }: { result: ResultState }) {
  const p = result.payload;

  if (result.tool === "prazo") {
    const venc = new Date(p.vencimento as string);
    const hoje = new Date();
    const diasFaltam = Math.ceil((venc.getTime() - hoje.getTime()) / (1000 * 60 * 60 * 24));
    return (
      <>
        <div className="grid grid-cols-3 gap-3">
          <KPI label="Vencimento" value={venc.toLocaleDateString("pt-BR")} />
          <KPI label="Dias úteis" value={String(p.diasUteis)} />
          <KPI label="Dias corridos" value={String(p.diasCorridos)} />
        </div>
        <div>
          <div className="mb-1 text-[11px] uppercase tracking-wider text-muted-foreground">Status</div>
          <Badge variant="outline" className={diasFaltam < 0 ? "border-rose-500/50 text-rose-600" : diasFaltam <= 3 ? "border-amber-500/50 text-amber-600" : "border-emerald-500/50 text-emerald-600"}>
            {diasFaltam < 0 ? `Vencido há ${Math.abs(diasFaltam)} dias` : `${diasFaltam} dias restantes`}
          </Badge>
        </div>
        <ObservacoesList obs={result.observacoes} />
      </>
    );
  }
  if (result.tool === "correcao") {
    return (
      <>
        <div className="grid grid-cols-2 gap-3">
          <KPI label="Valor original" value={fmtMoeda(Number(p.valorOriginal))} />
          <KPI label="Valor corrigido" value={fmtMoeda(Number(p.valorCorrigido))} accent="emerald" />
        </div>
        <div className="rounded-lg border border-border p-3 text-xs">
          <div className="font-semibold text-muted-foreground">Memória de cálculo</div>
          <div className="mt-1 font-mono text-[11px]">{String(p.memoriaCalculo)}</div>
          <div className="mt-1 text-[10px] text-muted-foreground">Índice: {String(p.indiceUsado)} · Fator: {Number(p.fatorCorrecao).toFixed(4)}</div>
        </div>
        <ObservacoesList obs={result.observacoes} />
      </>
    );
  }
  if (result.tool === "juros") {
    return (
      <>
        <div className="grid grid-cols-2 gap-3">
          <KPI label="Juros" value={fmtMoeda(Number(p.valorJuros))} />
          <KPI label="Total (principal + juros)" value={fmtMoeda(Number(p.valorTotal))} accent="emerald" />
        </div>
        <div className="rounded-lg border border-border p-3 text-xs">
          <div className="font-semibold text-muted-foreground">Memória</div>
          <div className="mt-1 font-mono text-[11px]">{String(p.memoriaCalculo)}</div>
          <div className="mt-1 text-[10px] text-muted-foreground">Base: {String(p.base)} · Taxa: {(Number(p.taxaMensal) * 100).toFixed(2)}% a.m. · Meses: {String(p.meses)}</div>
        </div>
      </>
    );
  }
  if (result.tool === "prescricao") {
    const prescrito = Boolean(p.prescrito);
    return (
      <>
        <div className={`rounded-lg border p-4 ${prescrito ? "border-rose-500/50 bg-rose-500/5" : "border-emerald-500/50 bg-emerald-500/5"}`}>
          <div className="flex items-center gap-2">
            {prescrito ? <AlertTriangle className="h-5 w-5 text-rose-600" /> : <CheckCircle2 className="h-5 w-5 text-emerald-600" />}
            <span className={`text-sm font-bold ${prescrito ? "text-rose-700 dark:text-rose-400" : "text-emerald-700 dark:text-emerald-400"}`}>
              {prescrito ? "PRESCRITO" : "Não prescrito"}
            </span>
          </div>
          <div className="mt-2 text-xs text-muted-foreground">{String(p.baseNormativa)}</div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <KPI label="Prazo prescricional" value={`${String(p.prazoPrescricional)} anos`} />
          <KPI label="Dias restantes" value={p.diasRestantes != null ? String(p.diasRestantes) : "—"} />
        </div>
        <ObservacoesList obs={result.observacoes} />
      </>
    );
  }
  // Resultado genérico
  return (
    <>
      <div className="rounded-lg border border-border p-3">
        <pre className="max-h-72 overflow-auto text-[11px] scrollbar-juridia">{JSON.stringify(p, null, 2)}</pre>
      </div>
      <ObservacoesList obs={result.observacoes} />
    </>
  );
}

function KPI({ label, value, accent }: { label: string; value: string; accent?: "emerald" }) {
  return (
    <div className={`rounded-lg border p-3 ${accent === "emerald" ? "border-emerald-500/40 bg-emerald-500/5" : "border-border"}`}>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={`mt-1 text-sm font-bold ${accent === "emerald" ? "text-emerald-700 dark:text-emerald-400" : ""}`}>{value}</div>
    </div>
  );
}

function ObservacoesList({ obs }: { obs?: string[] }) {
  if (!obs || obs.length === 0) return null;
  return (
    <div>
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Observações</div>
      <ul className="space-y-1">
        {obs.map((o, i) => (
          <li key={i} className="flex items-start gap-2 text-xs text-muted-foreground">
            <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-amber-500" />
            <span>{o}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ── Lógica das 5 ferramentas secundárias (determinística, client-side) ──────

function buildSalvaguardas(texto: string, area: string) {
  const lower = texto.toLowerCase();
  const clausulas: { nome: string; presente: boolean; recomendado: boolean }[] = [
    { nome: "Cláusula de foro (eleição de foro)", presente: lower.includes("foro"), recomendado: true },
    { nome: "Cláusula de arbitragem", presente: lower.includes("arbitragem"), recomendado: area === "empresarial" },
    { nome: "Cláusula de multa (penal)", presente: lower.includes("multa") || lower.includes("penal"), recomendado: true },
    { nome: "Cláusula de juros e correção", presente: lower.includes("juros") && lower.includes("corre"), recomendado: true },
    { nome: "Cláusula de indisponibilidade", presente: lower.includes("indispon"), recomendado: false },
    { nome: "Cláusula de renúncia (renúncia a direito)", presente: lower.includes("renúncia") || lower.includes("renuncia"), recomendado: area === "consumer" ? false : true },
    { nome: "Cláusula de prazo de carência", presente: lower.includes("carência") || lower.includes("carencia"), recomendado: true },
    { nome: "Cláusula de retirada de dados (LGPD)", presente: lower.includes("lgpd") || lower.includes("dados pessoais"), recomendado: true },
  ];
  const presentes = clausulas.filter((c) => c.presente).length;
  const obs = [
    `Detectadas ${presentes} de ${clausulas.length} cláusulas de salvaguarda.`,
    area === "consumer" && "CDC art. 51: cláusulas abusivas são nulas — evitar renúncia prévia de direito.",
    "Recomendado: cláusulas de multa (até 2% do contrato), foro (apenas se não abusiva), correção e juros explícitos.",
    "⚠ Verifique LGPD art. 7º para tratamento de dados pessoais em contratos.",
  ].filter(Boolean) as string[];
  return {
    payload: {
      clausulas,
      presentes,
      total: clausulas.length,
      cobertura: Math.round((presentes / clausulas.length) * 100),
    },
    observacoes: obs,
  };
}

function checkValorCausa(valor: number, pedidos: string, area: string) {
  const obs: string[] = [];
  let status: "ok" | "risco" | "erro" = "ok";
  let motivo = "";

  if (!valor || valor <= 0) {
    status = "erro";
    motivo = "Valor da causa não informado ou zero — art. 291 CPC exige indicação.";
    obs.push("⚠ Art. 291 CPC: a petição inicial indicará o valor da causa.");
    obs.push("⚠ Art. 292 CPC: se pedido é indenização, valor da causa deve ser quantia pretendida.");
  } else if (area === "trabalhista" && valor > 40) {
    obs.push("CLT: valor da causa não é exigido como em cível, mas pelo número de salários.");
  } else {
    obs.push(`Valor da causa: ${fmtMoeda(valor)}`);
    obs.push("Verificar compatibilidade com pedido (art. 292 CPC).");
    if (pedidos.toLowerCase().includes("indeniz") && valor < 18800) {
      status = "risco";
      motivo = "Pedido de indenização com valor da causa abaixo de 1 salário-mínimo anual — pode indicar subavaliação.";
      obs.push("⚠ Verificar se valor reflete pretensão integral (art. 292, II CPC).");
    } else {
      motivo = "Valor da causa indicado e compatível com pedido aparente.";
    }
  }
  obs.push("⚠ Impugnação ao valor da causa: art. 293 CPC (autuado em apartado).");
  obs.push("⚠ Efeito da impugnação: suspende o processo até decisão (art. 293, §1º).");
  return { payload: { status, motivo, valor, pedidos }, observacoes: obs };
}

function triagemRisco(form: { fatos: string; area: string; valorCausa: string; provas: string }) {
  const lower = (form.fatos + " " + form.provas).toLowerCase();
  let risco = 0;
  const flags: string[] = [];
  if (lower.includes("prescri") || lower.includes("decadência") || lower.includes("decadencia")) { risco += 30; flags.push("prescrição/decadência"); }
  if (lower.includes("sem prova") || lower.includes("difícil prova") || lower.includes("dificil prova") || lower.includes("sem documento")) { risco += 25; flags.push("dificuldade probatória"); }
  if (lower.includes("jurisprudência divergente") || lower.includes("tese nova") || lower.includes("inédito")) { risco += 20; flags.push("tese divergente/inédita"); }
  if (lower.includes("tutela") || lower.includes("liminar") || lower.includes("urgência") || lower.includes("urgencia")) { risco += 15; flags.push("tutela de urgência requerida"); }
  if (form.provas.toLowerCase().includes("testemunh") && !lower.includes("documental")) { risco += 10; flags.push("prova exclusivamente testemunhal"); }
  if (!form.fatos || form.fatos.length < 50) { risco += 15; flags.push("fatos insuficientes"); }
  const nivel = risco >= 50 ? "alto" : risco >= 25 ? "medio" : "baixo";
  const obs = [
    `Nível de risco: ${nivel.toUpperCase()} (${risco}/100)`,
    `Sinais detectados: ${flags.length > 0 ? flags.join(", ") : "nenhum sinal relevante"}`,
    `Área: ${form.area}`,
    "⚠ Triagem é heurística — confirmar com análise completa do Cérebro.",
  ];
  return { payload: { risco, nivel, flags }, observacoes: obs };
}

function checkVedacaoSurpresa(form: { decisao: string; partes: string; fundamentos: string }) {
  const obs: string[] = [];
  const decisaoLower = form.decisao.toLowerCase();
  const partesHeard = form.partes.toLowerCase().trim();
  let status: "ok" | "risco" | "erro" = "ok";
  let motivo = "Sem indícios de decisão surpresa.";

  if (decisaoLower.length < 10) {
    status = "erro";
    motivo = "Descreva a decisão pretendida.";
  } else if (partesHeard.startsWith("não") || partesHeard.startsWith("nao") || partesHeard === "n") {
    status = "erro";
    motivo = "VEDAÇÃO: art. 10 CPC proíbe decisão surpresa — partes não foram ouvidas.";
    obs.push("⛔ Art. 10, §1º CPC: nenhuma decisão será proferida sem prévio contraditório.");
    obs.push("⛔ Art. 9º CPC: devem ser ouvidos antes da prática de ato que possa causar prejuízo.");
  } else if (partesHeard.startsWith("parc") || partesHeard.includes("parcial")) {
    status = "risco";
    motivo = "Partes ouvidas parcialmente — risco de decisão surpresa.";
    obs.push("⚠ Verificar se todas as questões relevantes foram submetidas ao contraditório.");
  } else {
    obs.push("✓ Partes foram ouvidas previamente (art. 10 CPC).");
  }

  obs.push(`Fundamentos invocados: ${form.fundamentos || "(não informado)"}`);
  if (decisaoLower.includes("extin")) {
    obs.push("⚠ Extinção do processo: art. 485 CPC — verificar motivo (inciso IV ou V) e contraditório prévio.");
  }
  if (decisaoLower.includes("improced") || decisaoLower.includes("proced")) {
    obs.push("⚠ Julgamento de mérito: art. 488/489 CPC — verificar revelia, prova e contestação.");
  }
  return {
    payload: { status, motivo, partes: form.partes },
    observacoes: obs,
  };
}

function checklistJulgador(form: { fatos: string; area: string; valorCausa: string; provas: string }) {
  const lower = (form.fatos + " " + form.provas).toLowerCase();
  const checks = [
    { item: "Competência (art. 42-62 CPC)", status: lower.includes("vara") || lower.includes("comarca") ? "ok" : "risco" as const },
    { item: "Legitimidade das partes (art. 17 CPC)", status: lower.includes("autor") && lower.includes("réu") ? "ok" : "risco" as const },
    { item: "Interesse processual (art. 17 §1º)", status: "risco" as const },
    { item: "Condições da ação (art. 17 + 325)", status: "risco" as const },
    { item: "Valor da causa (art. 291-294 CPC)", status: form.valorCausa ? "ok" as const : "erro" as const },
    { item: "Prescrição (art. 337 §1º)", status: lower.includes("prescri") ? "risco" as const : "ok" as const },
    { item: "Preliminares (art. 337 CPC)", status: "ok" as const },
    { item: "Pedido determinado (art. 319 CPC)", status: lower.includes("pedido") || lower.includes("pede") ? "ok" as const : "risco" as const },
    { item: "Fatos narrados (art. 319, II)", status: form.fatos.length > 50 ? "ok" as const : "erro" as const },
    { item: "Fundamentos jurídicos (art. 319, III)", status: "risco" as const },
  ];
  const okCount = checks.filter((c) => c.status === "ok").length;
  const erroCount = checks.filter((c) => c.status === "erro").length;
  const riscoCount = checks.filter((c) => c.status === "risco").length;
  const obs = [
    `Checklist: ${okCount} ok · ${riscoCount} risco · ${erroCount} erro (de ${checks.length})`,
    erroCount > 0 ? "⚠ Há bloqueios de admissibilidade — corrigir antes de protocolar." : "✓ Sem bloqueios de admissibilidade aparentes.",
    riscoCount > 0 ? `⚠ ${riscoCount} pontos exigem confirmação manual.` : "✓ Sem pontos de risco aparentes.",
    "⚠ Checklist é heurística — complementar com Simulação de Julgador (LLM).",
  ];
  return {
    payload: { checks, okCount, riscoCount, erroCount, total: checks.length, admissivel: erroCount === 0 },
    observacoes: obs,
  };
}
