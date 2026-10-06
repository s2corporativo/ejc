// WizardPeticao.tsx — Wizard linear de geração de petição em 5 passos.
//
// 1. Escolher template
// 2. Preencher fatos (form dinâmico baseado no template)
// 3. Contexto adicional (opcional: precedentes, testemunhas, valor da causa)
// 4. Validar (verificações automáticas de completude)
// 5. Gerar + download .md e .docx
//
// Consolida o pipeline PLANEJAR → REDIGIR → VERIFICAR em um único fluxo
// para o usuário que prefere wizard (estilo MinutaIA).

"use client";

import { useState, useMemo } from "react";
import {
  FileText,
  ChevronRight,
  ChevronLeft,
  Check,
  AlertTriangle,
  Loader2,
  Sparkles,
  Download,
  Copy,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "@/hooks/use-toast";
import { TEMPLATES, type TemplateDef } from "@/lib/templates_catalog";

type Step = 1 | 2 | 3 | 4 | 5;

interface FormData {
  templateSlug: string;
  fatos: string;
  valorCausa: string;
  pedidosExtras: string;
  precedentes: string;
}

interface ValidationResult {
  ok: boolean;
  warnings: string[];
  errors: string[];
}

const PASSOS: { step: Step; titulo: string; descricao: string }[] = [
  { step: 1, titulo: "Escolher template", descricao: "Selecione o tipo de peça a ser gerada" },
  { step: 2, titulo: "Fatos e partes", descricao: "Descreva os fatos e identifique as partes" },
  { step: 3, titulo: "Contexto adicional", descricao: "Valor da causa, pedidos extras, precedentes" },
  { step: 4, titulo: "Validação", descricao: "Verificações automáticas de completude" },
  { step: 5, titulo: "Gerar peça", descricao: "Resultado em .md e .docx" },
];

export function WizardPeticao() {
  const [step, setStep] = useState<Step>(1);
  const [form, setForm] = useState<FormData>({
    templateSlug: "",
    fatos: "",
    valorCausa: "",
    pedidosExtras: "",
    precedentes: "",
  });
  const [gerado, setGerado] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const template = useMemo<TemplateDef | undefined>(
    () => TEMPLATES.find((t) => t.slug === form.templateSlug),
    [form.templateSlug],
  );

  const validation = useMemo<ValidationResult>(() => {
    const errors: string[] = [];
    const warnings: string[] = [];
    if (!form.templateSlug) errors.push("Selecione um template no passo 1");
    if (!form.fatos || form.fatos.trim().length < 50) errors.push("Descreva os fatos (mínimo 50 caracteres)");
    if (form.fatos && form.fatos.trim().length < 200) {
      warnings.push("Fatos muito curtos. Recomendamos >= 200 caracteres para gerar uma boa peça");
    }
    if (template?.campos.includes("valorCausa") && !form.valorCausa) {
      errors.push("Valor da causa é obrigatório para este template (CPC art. 291-294)");
    }
    if (!form.pedidosExtras) {
      warnings.push("Considere detalhar os pedidos para gerar petição mais precisa");
    }
    return { ok: errors.length === 0, errors, warnings };
  }, [form, template]);

  function next() {
    if (step < 5) setStep((step + 1) as Step);
  }
  function back() {
    if (step > 1) setStep((step - 1) as Step);
  }

  async function gerar() {
    if (!template) {
      setError("Selecione um template");
      return;
    }
    setLoading(true);
    setError(null);
    setGerado(null);
    try {
      const res = await fetch("/api/gerar-contraria", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          caseId: null,
          areaJuridica: template.area,
          textoPeca: form.fatos,
          fatosCaso: form.fatos,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: "Erro" }));
        throw new Error(err.error || "Falha ao gerar");
      }
      const data = (await res.json()) as { raw?: string; contestacao?: string; analise?: string };
      setGerado(data.raw ?? data.contestacao ?? data.analise ?? "(sem conteúdo)");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function baixarDocx() {
    if (!gerado) return;
    try {
      const res = await fetch("/api/export/docx", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          markdown: gerado,
          titulo: template?.nome,
          autor: "Advogado",
          oab: "OAB/MG 000000",
          filename: template?.slug || "minuta",
        }),
      });
      if (!res.ok) throw new Error("Falha ao gerar .docx");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${template?.slug || "minuta"}.docx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast({ title: "Download .docx iniciado" });
    } catch (e) {
      toast({ title: "Erro", description: (e as Error).message, variant: "destructive" });
    }
  }

  function copiar() {
    if (gerado) {
      navigator.clipboard.writeText(gerado);
      toast({ title: "Copiado para a área de transferência" });
    }
  }

  return (
    <div className="container-juridia space-y-6 py-6">
      <header className="space-y-2">
        <div className="flex items-center gap-2">
          <FileText className="h-5 w-5 text-primary" />
          <h1 className="text-2xl font-bold">Wizard de Petição</h1>
          <Badge variant="outline" className="text-[10px]">5 passos</Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          Fluxo guiado: escolha o template, descreva os fatos, valide e gere a peça.
        </p>
      </header>

      <Stepper step={step} />

      {/* PASSO 1 — Escolher template */}
      {step === 1 && (
        <Card>
          <CardHeader>
            <CardTitle>1. Escolher template</CardTitle>
            <CardDescription>{TEMPLATES.length} modelos curados. Tags "core" são os mais comuns.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {TEMPLATES.map((t) => (
                <button
                  key={t.slug}
                  type="button"
                  onClick={() => setForm((f) => ({ ...f, templateSlug: t.slug }))}
                  className={`rounded-lg border p-3 text-left transition hover:border-primary ${
                    form.templateSlug === t.slug ? "border-primary bg-primary/5" : "border-border"
                  }`}
                >
                  <div className="mb-1 flex items-center gap-2">
                    <span className="font-semibold text-sm">{t.nome}</span>
                    {t.tags.includes("core") && <Badge variant="secondary" className="text-[8px]">core</Badge>}
                  </div>
                  <p className="text-[11px] text-muted-foreground">{t.descricao}</p>
                  <p className="mt-1 text-[10px] text-muted-foreground">Área: {t.area}</p>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* PASSO 2 — Fatos */}
      {step === 2 && (
        <Card>
          <CardHeader>
            <CardTitle>2. Fatos e partes</CardTitle>
            <CardDescription>Para o template: {template?.nome ?? "(nenhum)"}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs">Fatos do caso *</Label>
              <Textarea
                rows={12}
                value={form.fatos}
                onChange={(e) => setForm((f) => ({ ...f, fatos: e.target.value }))}
                placeholder="Descreva os fatos em ordem cronológica. Use [NOME_1] para pseudonimizar dados pessoais."
              />
              <p className="text-[10px] text-muted-foreground">
                {form.fatos.length} caracteres · Recomendado: >= 200 para peça robusta
              </p>
            </div>
            {template?.campos.includes("valorCausa") && (
              <div className="space-y-1.5">
                <Label className="text-xs">Valor da causa *</Label>
                <Input
                  value={form.valorCausa}
                  onChange={(e) => setForm((f) => ({ ...f, valorCausa: e.target.value }))}
                  placeholder="R$ 50.000,00"
                />
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* PASSO 3 — Contexto adicional */}
      {step === 3 && (
        <Card>
          <CardHeader>
            <CardTitle>3. Contexto adicional</CardTitle>
            <CardDescription>Opcional mas recomendado para peças mais precisas.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs">Pedidos extras (opcional)</Label>
              <Textarea
                rows={3}
                value={form.pedidosExtras}
                onChange={(e) => setForm((f) => ({ ...f, pedidosExtras: e.target.value }))}
                placeholder="Liste pedidos adicionais além do principal (ex: tutela de urgência, justiça gratuita)"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Precedentes sugeridos (opcional)</Label>
              <Textarea
                rows={3}
                value={form.precedentes}
                onChange={(e) => setForm((f) => ({ ...f, precedentes: e.target.value }))}
                placeholder="Súmulas, temas STF/STJ, ou precedentes específicos que devem ser citados (um por linha)"
              />
            </div>
          </CardContent>
        </Card>
      )}

      {/* PASSO 4 — Validação */}
      {step === 4 && (
        <Card>
          <CardHeader>
            <CardTitle>4. Validação automática</CardTitle>
            <CardDescription>Verificações pré-geração para reduzir erros formais.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {validation.errors.length === 0 && validation.warnings.length === 0 ? (
              <div className="flex items-center gap-2 text-sm text-emerald-600">
                <Check className="h-4 w-4" /> Tudo ok! Pronto para gerar.
              </div>
            ) : (
              <>
                {validation.errors.map((e, i) => (
                  <div key={`e${i}`} className="flex items-start gap-2 rounded-md border border-rose-300 bg-rose-50 p-2 text-xs text-rose-800">
                    <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
                    <span>{e}</span>
                  </div>
                ))}
                {validation.warnings.map((w, i) => (
                  <div key={`w${i}`} className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-2 text-xs text-amber-800">
                    <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
                    <span>{w}</span>
                  </div>
                ))}
              </>
            )}
          </CardContent>
        </Card>
      )}

      {/* PASSO 5 — Gerar */}
      {step === 5 && (
        <Card>
          <CardHeader>
            <CardTitle>5. Gerar peça</CardTitle>
            <CardDescription>{template?.nome} · {template?.area}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {!gerado ? (
              <div className="space-y-3">
                <Button onClick={gerar} disabled={loading || !validation.ok} size="lg" className="w-full">
                  {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}
                  Gerar peça
                </Button>
                {error && (
                  <div className="rounded-md border border-rose-300 bg-rose-50 p-2 text-sm text-rose-800">
                    {error}
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-3">
                <div className="rounded-md border border-green-300 bg-green-50 p-3 text-sm text-green-900">
                  <strong>Peça gerada.</strong> Lembre-se: trata-se de RASCUNHO para revisão humana antes do protocolo.
                </div>
                <div className="rounded-lg border border-border p-3">
                  <pre className="max-h-[28rem] overflow-auto whitespace-pre-wrap text-[11px] leading-relaxed scrollbar-juridia">
                    {gerado}
                  </pre>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button onClick={baixarDocx} variant="default">
                    <Download className="mr-2 h-4 w-4" /> Baixar .docx
                  </Button>
                  <Button onClick={copiar} variant="outline">
                    <Copy className="mr-2 h-4 w-4" /> Copiar .md
                  </Button>
                  <Button onClick={() => { setGerado(null); setStep(1); }} variant="ghost">
                    Novo
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* NAVEGAÇÃO */}
      <div className="flex items-center justify-between">
        <Button onClick={back} disabled={step === 1} variant="outline">
          <ChevronLeft className="mr-2 h-4 w-4" /> Voltar
        </Button>
        {step < 5 ? (
          <Button onClick={next} disabled={step === 4 && !validation.ok}>
            Próximo <ChevronRight className="ml-2 h-4 w-4" />
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function Stepper({ step }: { step: Step }) {
  return (
    <div className="flex items-center gap-2 overflow-x-auto pb-2">
      {PASSOS.map((p) => {
        const done = p.step < step;
        const current = p.step === step;
        return (
          <div key={p.step} className="flex items-center gap-2">
            <div
              className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold ${
                done ? "bg-emerald-500 text-white" : current ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
              }`}
            >
              {done ? <Check className="h-3 w-3" /> : p.step}
            </div>
            <span className={`text-xs ${current ? "font-bold" : "text-muted-foreground"}`}>{p.titulo}</span>
            {p.step < 5 && <ChevronRight className="h-3 w-3 text-muted-foreground/40" />}
          </div>
        );
      })}
    </div>
  );
}