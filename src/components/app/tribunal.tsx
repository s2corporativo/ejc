// tribunal.tsx — Cérebro Jurídico Multi-Agente (Advogado + Juiz + Promotor).
//
// UI para conduzir um debate adversarial em 5 turnos. Cada turno
// aparece cronologicamente; o usuário acompanha a evolução do
// contraditório antes do protocolo.

"use client";

import { useEffect, useState } from "react";
import { Gavel, Scale, BookOpen, Send, Loader2, FileDown, ExternalLink, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { useAppStore } from "@/lib/store";
import { ensureDraftMarker } from "@/lib/ai_governance";
import type { PersonaSlug } from "@/lib/personas";

interface DebateTurnDto {
  id: string;
  debateId: string;
  turnNumber: number;
  persona: PersonaSlug;
  subRole: string;
  content: string;
  citations: { diploma: string; numero: string; url: string | null; verified: boolean }[];
  tokensUsed: number;
  latencyMs: number;
  createdAt: string;
}

interface DebateDto {
  id: string;
  caseId: string | null;
  ramoJuridico: string;
  factsInput: string;
  parteConfig: { lado?: "autor" | "reu"; parteAutora?: string; parteRe?: string } | null;
  status: string;
  inadmissibilidade: string | null;
  veredito: string | null;
  createdAt: string;
}

const RAMOS = [
  { id: "penal", label: "Penal" },
  { id: "processo_penal", label: "Processo Penal" },
  { id: "civil", label: "Civil" },
  { id: "processo_civil", label: "Processo Civil" },
  { id: "consumidor", label: "Consumidor" },
  { id: "trabalhista", label: "Trabalhista" },
  { id: "previdenciario", label: "Previdenciário" },
  { id: "tributario", label: "Tributário" },
  { id: "administrativo", label: "Administrativo" },
  { id: "ambiental", label: "Ambiental" },
  { id: "digital", label: "Digital (LGPD/MCI)" },
];

const PERSONA_META: Record<PersonaSlug, { nome: string; cor: string; icon: typeof Gavel; papel: string }> = {
  advogado: { nome: "Advogado", cor: "bg-blue-500/10 text-blue-700 border-blue-300", icon: BookOpen, papel: "Patrono da parte" },
  juiz: { nome: "Juiz", cor: "bg-purple-500/10 text-purple-700 border-purple-300", icon: Gavel, papel: "Estado-juiz" },
  promotor: { nome: "Promotor", cor: "bg-red-500/10 text-red-700 border-red-300", icon: Scale, papel: "Ministério Público" },
};

export function Tribunal() {
  const { currentCaseId, setActiveDebateId, activeDebateId } = useAppStore();
  const [facts, setFacts] = useState("");
  const [parteAutora, setParteAutora] = useState("[AUTOR_1]");
  const [parteRe, setParteRe] = useState("[REU_1]");
  const [ramoJuridico, setRamoJuridico] = useState("civil");
  const [ladoAdvogado, setLadoAdvogado] = useState<"autor" | "reu">("autor");

  const [debate, setDebate] = useState<DebateDto | null>(null);
  const [turns, setTurns] = useState<DebateTurnDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [finished, setFinished] = useState(false);

  // Se já tem debate ativo, carrega
  useEffect(() => {
    if (activeDebateId) loadDebate(activeDebateId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadDebate(id: string) {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/debate/${id}`);
      if (!res.ok) throw new Error("Debate não encontrado");
      const data = (await res.json()) as { debate: DebateDto; turns: DebateTurnDto[] };
      setDebate(data.debate);
      setTurns(data.turns);
      setFinished(data.debate.status === "concluido" || data.debate.status === "inadmitido");
      setActiveDebateId(id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }  async function startDebate() {
    if (!facts.trim()) {
      setError("Descreva os fatos do caso antes de iniciar o debate.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/debate/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          caseId: currentCaseId,
          ramoJuridico,
          facts: ensureDraftMarker(facts),
          parteAutora,
          parteRe,
          ladoAdvogado,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: "Erro desconhecido" }));
        throw new Error(err.error || "Falha ao iniciar debate");
      }
      const data = (await res.json()) as { debateId: string; turn: DebateTurnDto; finished?: boolean };
      setActiveDebateId(data.debateId);
      await loadDebate(data.debateId);
      void data.turn; // primeira carga já é via loadDebate
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function nextTurn() {
    if (!debate) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/debate/next", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ debateId: debate.id }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: "Erro desconhecido" }));
        throw new Error(err.error || "Falha ao avançar turno");
      }
      const data = (await res.json()) as { turn: DebateTurnDto; finished: boolean };
      setTurns((prev) => [...prev, data.turn]);
      setFinished(!!data.finished);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  function newDebate() {
    setDebate(null);
    setTurns([]);
    setFinished(false);
    setActiveDebateId(null);
  }

  function downloadArtifact(t: DebateTurnDto) {
    const blob = new Blob([t.content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const label = PERSONA_META[t.persona].nome.replace(/\s+/g, "-").toLowerCase();
    a.download = `tribunal-turno${t.turnNumber}-${label}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  return (
    <div className="container-juridia space-y-6 py-6">
      <header className="space-y-2">
        <div className="flex items-center gap-2">
          <Gavel className="h-5 w-5 text-primary" />
          <h1 className="text-2xl font-bold">Tribunal Multi-Agente</h1>
          <Badge variant="outline" className="text-[10px]">Cérebro Jurídico</Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          Três personas distintas (Advogado, Juiz, Promotor) debatem os mesmos fatos
          em até 5 turnos. Use para antecipar o contraditório antes do protocolo.
        </p>
      </header>

      {/* AVISO OBRIGATÓRIO OAB */}
      <div className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900">
        <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
        <div>
          <strong>Rascunho para revisão humana.</strong> Esta ferramenta simula o
          debate processual e produz minutas sujeitas à revisão do advogado
          habilitado (art. 1º EOAB). Não constitui aconselhamento jurídico nem
          promessa de resultado.
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </div>
      )}

      {/* CONFIGURAÇÃO (apenas quando não há debate) */}
      {!debate && (
        <Card>
          <CardHeader>
            <CardTitle>Configurar debate</CardTitle>
            <CardDescription>Informe os fatos e o ramo jurídico. O sistema pseudonimiza antes de chamar o LLM.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="text-xs font-medium">Parte autora</label>
                <Input value={parteAutora} onChange={(e) => setParteAutora(e.target.value)} placeholder="[AUTOR_1]" />
              </div>
              <div>
                <label className="text-xs font-medium">Parte ré</label>
                <Input value={parteRe} onChange={(e) => setParteRe(e.target.value)} placeholder="[REU_1]" />
              </div>
              <div>
                <label className="text-xs font-medium">Ramo jurídico</label>
                <Select value={ramoJuridico} onValueChange={setRamoJuridico}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {RAMOS.map((r) => (
                      <SelectItem key={r.id} value={r.id}>{r.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-xs font-medium">Advogado defende</label>
                <Select value={ladoAdvogado} onValueChange={(v) => setLadoAdvogado(v as "autor" | "reu")}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="autor">Autor</SelectItem>
                    <SelectItem value="reu">Réu</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <label className="text-xs font-medium">Fatos do caso</label>
              <Textarea
                value={facts}
                onChange={(e) => setFacts(e.target.value)}
                rows={8}
                placeholder="Descreva os fatos. Use [NOME_1], [CPF_1] para dados pessoais — o sistema pseudonimiza automaticamente."
              />
              <p className="mt-1 text-[10px] text-muted-foreground">
                {facts.length} caracteres · Será pseudonimizado antes do envio.
              </p>
            </div>
            <Button onClick={startDebate} disabled={loading} className="w-full">
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Gavel className="mr-2 h-4 w-4" />}
              Iniciar debate (turno 1: Advogado)
            </Button>
          </CardContent>
        </Card>
      )}

      {/* TIMELINE DE TURNOS */}
      {debate && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold">Debate #{debate.id.slice(0, 8)}</h2>
              <p className="text-xs text-muted-foreground">
                {RAMOS.find((r) => r.id === debate.ramoJuridico)?.label} · Status: <strong>{debate.status}</strong>
              </p>
            </div>
            <Button variant="outline" size="sm" onClick={newDebate}>Novo debate</Button>
          </div>

          <div className="space-y-3">
            {turns.map((t) => {
              const meta = PERSONA_META[t.persona];
              const Icon = meta.icon;
              return (
                <Card key={t.id} className={`border-l-4 ${meta.cor}`}>
                  <CardHeader className="flex flex-row items-start justify-between gap-2 space-y-0 pb-2">
                    <div className="flex items-center gap-2">
                      <Icon className="h-4 w-4" />
                      <div>
                        <CardTitle className="text-sm">Turno {t.turnNumber} — {meta.nome}</CardTitle>
                        <CardDescription className="text-[10px]">{meta.papel} · {t.subRole}</CardDescription>
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      <Badge variant="secondary" className="text-[10px]">{t.tokensUsed} tok</Badge>
                      <Button variant="ghost" size="sm" onClick={() => downloadArtifact(t)} title="Baixar .md">
                        <FileDown className="h-3 w-3" />
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <pre className="whitespace-pre-wrap break-words font-sans text-xs leading-relaxed">
                      {t.content}
                    </pre>
                    {t.citations.length > 0 && (
                      <div className="mt-3 border-t pt-2">
                        <p className="text-[10px] font-semibold uppercase text-muted-foreground">Citações ({t.citations.length})</p>
                        <ul className="mt-1 space-y-1">
                          {t.citations.map((c, i) => (
                            <li key={i} className="flex items-center gap-1 text-[10px]">
                              <span className="font-mono">{c.diploma} {c.numero}</span>
                              {c.url && <a href={c.url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline inline-flex items-center gap-0.5"><ExternalLink className="h-2.5 w-2.5" /> fonte</a>}
                              {!c.verified && <Badge variant="outline" className="text-[8px]">não verificado</Badge>}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>

          {!finished && turns.length < 5 && (
            <div className="flex justify-center">
              <Button onClick={nextTurn} disabled={loading} size="lg">
                {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
                {turns.length === 1 && "Avançar para turno 2 — Promotor"}
                {turns.length === 2 && "Avançar para turno 3 — Juiz (admissibilidade)"}
                {turns.length === 3 && "Avançar para turno 4 — Advogado (réplica)"}
                {turns.length === 4 && "Avançar para turno 5 — Juiz (sentença)"}
              </Button>
            </div>
          )}

          {finished && (
            <div className="rounded-md border border-green-300 bg-green-50 p-3 text-sm text-green-900">
              <strong>Debate concluído.</strong> {debate.inadmissibilidade ? "O Juiz inadmitiu a inicial — reveja os pressupostos processuais antes de protocolar." : "Todos os artefatos foram gerados. Baixe cada peça em .md e submeta à revisão humana."}
            </div>
          )}
        </div>
      )}
    </div>
  );
}