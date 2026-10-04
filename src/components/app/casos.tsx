"use client";

import { useEffect, useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Briefcase,
  Plus,
  Trash2,
  Edit3,
  Search,
  CheckCircle2,
  Circle,
  Loader2,
  Users,
  Calendar,
  ArrowRight,
  FileText,
  Gavel,
  Clock,
  Flag,
  DollarSign,
  X,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { useAppStore } from "@/lib/store";
import { FluxoJuridico } from "./fluxo-juridico";
import { toast } from "@/hooks/use-toast";

// ── Tipos ──────────────────────────────────────────────────────────────────
interface Client { id: string; name: string; }
interface CaseItem {
  id: string;
  title: string;
  number: string | null;
  area: string;
  responsavel: string | null;
  prioridade: string;
  valor: string | null;
  status: string;
  dataDistribuicao: string | null;
  dataEncerramento: string | null;
  resultado: string | null;
  notes: string | null;
  processosVinculados: string[];
  clientId: string;
  clientName: string;
  documentsCount: number;
  movimentosCount: number;
  audienciasCount: number;
  createdAt: string;
  updatedAt: string;
}
interface Movimento { id: string; data: string; tipo: string; descricao: string; numeroProc: string | null; }
interface Audiencia { id: string; data: string; tipo: string; local: string | null; orgao: string | null; status: string; resultado: string | null; observacoes: string | null; }

const AREA_LABELS: Record<string, string> = {
  civil: "Cível", penal: "Penal", trabalhista: "Trabalhista", tributario: "Tributário",
  consumer: "Consumidor", family: "Família", previdenciario: "Previdenciário",
  empresarial: "Empresarial", administrativo: "Administrativo", bancario: "Bancário",
  ambiental: "Ambiental", digital_lgpd: "Digital/LGPD", transito: "Trânsito",
};

const PRIORIDADE_CONFIG: Record<string, { label: string; color: string }> = {
  alta: { label: "Alta", color: "text-red-600 bg-red-500/10 border-red-500/30" },
  media: { label: "Média", color: "text-amber-600 bg-amber-500/10 border-amber-500/30" },
  baixa: { label: "Baixa", color: "text-green-600 bg-green-500/10 border-green-500/30" },
};

const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  ativo: { label: "Ativo", color: "text-green-600" },
  suspenso: { label: "Suspenso", color: "text-amber-600" },
  encerrado: { label: "Encerrado", color: "text-muted-foreground" },
};

const TIPO_MOV_LABELS: Record<string, string> = {
  petition: "Petição", despacho: "Despacho", decisao: "Decisão", sentenca: "Sentença",
  recurso: "Recurso", audiencia: "Audiência", outro: "Outro",
};

const TIPO_AUD_LABELS: Record<string, string> = {
  conciliacao: "Conciliação", instrucao: "Instrução", julgamento: "Julgamento",
  oitiva: "Oitiva", outra: "Outra",
};

export function Casos() {
  const { setBrainContext, setAppTab } = useAppStore();
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("todos");
  const [areaFilter, setAreaFilter] = useState("todas");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingCase, setEditingCase] = useState<CaseItem | null>(null);
  const [selectedCase, setSelectedCase] = useState<CaseItem | null>(null);

  // Movimentações e audiências do caso selecionado
  const [movimentos, setMovimentos] = useState<Movimento[]>([]);
  const [audiencias, setAudiencias] = useState<Audiencia[]>([]);
  const [movForm, setMovForm] = useState({ tipo: "outro", descricao: "", numeroProc: "" });
  const [audForm, setAudForm] = useState({ data: "", tipo: "conciliacao", local: "", orgao: "", observacoes: "" });

  // Form do caso
  const [form, setForm] = useState({
    clientId: "", title: "", number: "", area: "civil", responsavel: "",
    prioridade: "media", valor: "", notes: "", dataDistribuicao: "", processosVinculados: "" ,
  });

  async function reload() {
    setLoading(true);
    try {
      const [cRes, clRes] = await Promise.all([fetch("/api/cases"), fetch("/api/clients")]);
      const cData = await cRes.json();
      const clData = await clRes.json();
      setCases(cData.cases || []);
      setClients(clData.clients?.map((c: { id: string; name: string }) => ({ id: c.id, name: c.name })) || []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }

  useEffect(() => { reload(); }, []);

  async function loadCaseDetails(caseId: string) {
    try {
      const [mRes, aRes] = await Promise.all([
        fetch(`/api/cases/movements?caseId=${caseId}`),
        fetch(`/api/cases/hearings?caseId=${caseId}`),
      ]);
      const mData = await mRes.json();
      const aData = await aRes.json();
      setMovimentos(mData.movimentos || []);
      setAudiencias(aData.audiencias || []);
    } catch { /* ignore */ }
  }

  const filtered = useMemo(() => {
    const q = filter.toLowerCase().trim();
    return cases.filter((c) => {
      if (statusFilter !== "todos" && c.status !== statusFilter) return false;
      if (areaFilter !== "todas" && c.area !== areaFilter) return false;
      if (!q) return true;
      return c.title.toLowerCase().includes(q) ||
        c.number?.toLowerCase().includes(q) ||
        c.clientName?.toLowerCase().includes(q) ||
        c.responsavel?.toLowerCase().includes(q);
    });
  }, [cases, filter, statusFilter, areaFilter]);

  function openNewCase() {
    setEditingCase(null);
    setForm({ clientId: "", title: "", number: "", area: "civil", responsavel: "", prioridade: "media", valor: "", notes: "", dataDistribuicao: "", processosVinculados: "" });
    setDialogOpen(true);
  }

  function openEditCase(c: CaseItem) {
    setEditingCase(c);
    setForm({
      clientId: c.clientId, title: c.title, number: c.number || "", area: c.area,
      responsavel: c.responsavel || "", prioridade: c.prioridade, valor: c.valor || "",
      notes: c.notes || "", dataDistribuicao: c.dataDistribuicao?.split("T")[0] || "",
      processosVinculados: c.processosVinculados?.join(", ") || "",
    });
    setDialogOpen(true);
  }

  async function saveCase() {
    if (!form.clientId) { toast({ title: "Selecione um cliente", variant: "destructive" }); return; }
    if (!form.title.trim()) { toast({ title: "Título obrigatório", variant: "destructive" }); return; }

    const payload = {
      ...form,
      processosVinculados: form.processosVinculados.split(",").map((s) => s.trim()).filter(Boolean),
    };

    try {
      if (editingCase) {
        await fetch("/api/cases", { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: editingCase.id, ...payload }) });
        toast({ title: "Caso atualizado" });
      } else {
        await fetch("/api/cases", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        toast({ title: "Caso criado" });
      }
      setDialogOpen(false);
      setEditingCase(null);
      reload();
    } catch { toast({ title: "Erro ao salvar", variant: "destructive" }); }
  }

  async function deleteCase(id: string) {
    if (!confirm("Excluir este caso e todos os dados vinculados?")) return;
    try {
      await fetch(`/api/cases?id=${id}`, { method: "DELETE" });
      toast({ title: "Caso excluído" });
      if (selectedCase?.id === id) setSelectedCase(null);
      reload();
    } catch { toast({ title: "Erro ao excluir", variant: "destructive" }); }
  }

  async function encerrarCaso(c: CaseItem) {
    const resultado = prompt("Resultado do caso (procedente/improcedente/acordo/extinto/parcial):", "acordo");
    if (!resultado) return;
    await fetch("/api/cases", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: c.id, status: "encerrado", dataEncerramento: new Date().toISOString(), resultado }),
    });
    toast({ title: "Caso encerrado", description: `Resultado: ${resultado}` });
    reload();
  }

  async function addMovimento() {
    if (!selectedCase || !movForm.descricao.trim()) return;
    await fetch("/api/cases/movements", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ caseId: selectedCase.id, ...movForm }),
    });
    setMovForm({ tipo: "outro", descricao: "", numeroProc: "" });
    loadCaseDetails(selectedCase.id);
    toast({ title: "Movimentação registrada" });
  }

  async function addAudiencia() {
    if (!selectedCase || !audForm.data) return;
    await fetch("/api/cases/hearings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ caseId: selectedCase.id, ...audForm }),
    });
    setAudForm({ data: "", tipo: "conciliacao", local: "", orgao: "", observacoes: "" });
    loadCaseDetails(selectedCase.id);
    toast({ title: "Audiência agendada" });
  }

  async function delMovimento(id: string) {
    await fetch(`/api/cases/movements?id=${id}`, { method: "DELETE" });
    if (selectedCase) loadCaseDetails(selectedCase.id);
  }

  async function delAudiencia(id: string) {
    await fetch(`/api/cases/hearings?id=${id}`, { method: "DELETE" });
    if (selectedCase) loadCaseDetails(selectedCase.id);
  }

  function openCaseDetails(c: CaseItem) {
    setSelectedCase(c);
    loadCaseDetails(c.id);
  }

  function sendToIntelligence(c: CaseItem) {
    const ctx = `CASO: ${c.title}\nCLIENTE: ${c.clientName}\nÁREA: ${AREA_LABELS[c.area] || c.area}\nRESPONSÁVEL: ${c.responsavel || "—"}\nVALOR: ${c.valor || "—"}\nNÚMERO: ${c.number || "—"}\nNOTAS: ${c.notes || "—"}`;
    setBrainContext(ctx);
    setAppTab("intelligence");
    toast({ title: "Caso enviado para Inteligência IA", description: "Os dados do caso serão usados como contexto" });
  }

  return (
    <div className="container-juridia py-8">
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Casos</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {cases.length} caso(s) · {cases.filter(c => c.status === "ativo").length} ativo(s) · {cases.filter(c => c.status === "encerrado").length} encerrado(s)
          </p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button onClick={openNewCase}><Plus className="mr-2 h-4 w-4" /> Novo caso</Button>
          </DialogTrigger>
          <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto scrollbar-juridia">
            <DialogHeader><DialogTitle>{editingCase ? "Editar caso" : "Novo caso"}</DialogTitle></DialogHeader>
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label className="text-xs">Cliente *</Label>
                <Select value={form.clientId} onValueChange={(v) => setForm(s => ({ ...s, clientId: v }))}>
                  <SelectTrigger><SelectValue placeholder="Selecione..." /></SelectTrigger>
                  <SelectContent>{clients.map((cl) => <SelectItem key={cl.id} value={cl.id}>{cl.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Título do caso *</Label>
                <Input value={form.title} onChange={(e) => setForm(s => ({ ...s, title: e.target.value }))} placeholder="Ex: Ação indenizatória" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs">Nº do processo</Label>
                  <Input value={form.number} onChange={(e) => setForm(s => ({ ...s, number: e.target.value }))} placeholder="0000000-00.0000.0.00.0000" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Área</Label>
                  <Select value={form.area} onValueChange={(v) => setForm(s => ({ ...s, area: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>{Object.entries(AREA_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs">Responsável</Label>
                  <Input value={form.responsavel} onChange={(e) => setForm(s => ({ ...s, responsavel: e.target.value }))} placeholder="Advogado" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Prioridade</Label>
                  <Select value={form.prioridade} onValueChange={(v) => setForm(s => ({ ...s, prioridade: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="alta">Alta</SelectItem>
                      <SelectItem value="media">Média</SelectItem>
                      <SelectItem value="baixa">Baixa</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs">Valor da causa</Label>
                  <Input value={form.valor} onChange={(e) => setForm(s => ({ ...s, valor: e.target.value }))} placeholder="R$ 0.000,00" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Distribuição</Label>
                  <Input type="date" value={form.dataDistribuicao} onChange={(e) => setForm(s => ({ ...s, dataDistribuicao: e.target.value }))} />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Processos vinculados (separe por vírgula)</Label>
                <Input value={form.processosVinculados} onChange={(e) => setForm(s => ({ ...s, processosVinculados: e.target.value }))} placeholder="0000000-00.0000.0.00.0000, ..." />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Observações</Label>
                <Textarea rows={2} value={form.notes} onChange={(e) => setForm(s => ({ ...s, notes: e.target.value }))} />
              </div>
              <Button onClick={saveCase} className="w-full">{editingCase ? "Salvar alterações" : "Criar caso"}</Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* Filtros */}
      <div className="mb-4 flex flex-wrap gap-2">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Buscar..." className="pl-9" />
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[130px]"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="todos">Todos status</SelectItem>
            <SelectItem value="ativo">Ativo</SelectItem>
            <SelectItem value="suspenso">Suspenso</SelectItem>
            <SelectItem value="encerrado">Encerrado</SelectItem>
          </SelectContent>
        </Select>
        <Select value={areaFilter} onValueChange={setAreaFilter}>
          <SelectTrigger className="w-[140px]"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="todas">Todas áreas</SelectItem>
            {Object.entries(AREA_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {loading ? (
        <div className="flex h-48 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
      ) : filtered.length === 0 ? (
        <Card><CardContent className="flex flex-col items-center gap-3 py-16 text-center">
          <Briefcase className="h-12 w-12 text-muted-foreground/40" />
          <div><h3 className="font-semibold">Nenhum caso encontrado</h3><p className="mt-1 text-sm text-muted-foreground">{filter || statusFilter !== "todos" ? "Tente outros filtros" : "Cadastre seu primeiro caso"}</p></div>
          <Button onClick={openNewCase}><Plus className="mr-2 h-4 w-4" /> Novo caso</Button>
        </CardContent></Card>
      ) : (
        <div className="space-y-3">
          {filtered.map((c, i) => (
            <motion.div key={c.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.03, 0.3) }}>
              <Card className={selectedCase?.id === c.id ? "ring-1 ring-primary/30" : ""}>
                <CardContent className="p-4">
                  <div className="flex items-start justify-between gap-3">
                    <button onClick={() => openCaseDetails(c)} className="flex-1 text-left">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-semibold">{c.title}</h3>
                        <Badge variant="outline" className="text-[10px]">{AREA_LABELS[c.area] || c.area}</Badge>
                        <Badge variant="outline" className={`text-[10px] ${PRIORIDADE_CONFIG[c.prioridade]?.color || ""}`}>
                          <Flag className="mr-1 h-2.5 w-2.5" />{PRIORIDADE_CONFIG[c.prioridade]?.label || c.prioridade}
                        </Badge>
                        <span className={`text-[10px] font-medium ${STATUS_CONFIG[c.status]?.color || ""}`}>● {STATUS_CONFIG[c.status]?.label || c.status}</span>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                        <span className="flex items-center gap-1"><Users className="h-3 w-3" />{c.clientName}</span>
                        {c.responsavel && <span className="flex items-center gap-1"><Briefcase className="h-3 w-3" />{c.responsavel}</span>}
                        {c.number && <span className="font-mono text-[10px]">{c.number}</span>}
                        {c.valor && <span className="flex items-center gap-1"><DollarSign className="h-3 w-3" />{c.valor}</span>}
                        <span className="flex items-center gap-1"><FileText className="h-3 w-3" />{c.documentsCount} doc(s)</span>
                        <span className="flex items-center gap-1"><Clock className="h-3 w-3" />{c.movimentosCount} mov.</span>
                        <span className="flex items-center gap-1"><Calendar className="h-3 w-3" />{c.audienciasCount} aud.</span>
                      </div>
                      {c.processosVinculados.length > 0 && (
                        <div className="mt-1 text-[10px] text-muted-foreground">Processos vinculados: {c.processosVinculados.join(", ")}</div>
                      )}
                      {c.resultado && <div className="mt-1 text-[10px] font-medium text-green-600">Resultado: {c.resultado}</div>}
                    </button>
                    <div className="flex gap-1">
                      <Button size="icon" variant="ghost" onClick={() => sendToIntelligence(c)} title="Enviar para IA">
                        <ArrowRight className="h-4 w-4 text-primary" />
                      </Button>
                      <Button size="icon" variant="ghost" onClick={() => openEditCase(c)} title="Editar"><Edit3 className="h-4 w-4" /></Button>
                      {c.status === "ativo" && (
                        <Button size="icon" variant="ghost" onClick={() => encerrarCaso(c)} title="Encerrar"><CheckCircle2 className="h-4 w-4 text-green-600" /></Button>
                      )}
                      <Button size="icon" variant="ghost" onClick={() => deleteCase(c.id)} title="Excluir"><Trash2 className="h-4 w-4" /></Button>
                    </div>
                  </div>

                  {/* Detalhes do caso (movimentações + audiências) */}
                  <AnimatePresence>
                    {selectedCase?.id === c.id && (
                      <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}>
                        <div className="mt-3 border-t border-border pt-3 space-y-3">
                          {/* Fluxo jurídico completo */}
                          <FluxoJuridico
                            caseTitle={c.title}
                            caseFacts={c.notes || `${c.title} — ${c.clientName} — ${AREA_LABELS[c.area] || c.area} — ${c.number || "sem número"}`}
                          />
                          <Tabs defaultValue="movimentos">
                            <TabsList className="h-8">
                              <TabsTrigger value="movimentos" className="text-xs">Movimentações ({movimentos.length})</TabsTrigger>
                              <TabsTrigger value="audiencias" className="text-xs">Audiências ({audiencias.length})</TabsTrigger>
                            </TabsList>

                            <TabsContent value="movimentos" className="mt-2">
                              <div className="mb-2 flex gap-2">
                                <Select value={movForm.tipo} onValueChange={(v) => setMovForm(s => ({ ...s, tipo: v }))}>
                                  <SelectTrigger className="w-[120px] h-8 text-xs"><SelectValue /></SelectTrigger>
                                  <SelectContent>{Object.entries(TIPO_MOV_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
                                </Select>
                                <Input value={movForm.descricao} onChange={(e) => setMovForm(s => ({ ...s, descricao: e.target.value }))} placeholder="Descrição da movimentação..." className="h-8 text-xs flex-1" />
                                <Button size="sm" onClick={addMovimento} disabled={!movForm.descricao.trim()}>Adicionar</Button>
                              </div>
                              {movimentos.length === 0 ? (
                                <p className="py-3 text-center text-xs text-muted-foreground">Nenhuma movimentação.</p>
                              ) : (
                                <div className="space-y-1.5 max-h-48 overflow-y-auto scrollbar-juridia">
                                  {movimentos.map((m) => (
                                    <div key={m.id} className="flex items-center gap-2 rounded border border-border p-2 text-xs">
                                      <Badge variant="secondary" className="text-[10px]">{TIPO_MOV_LABELS[m.tipo] || m.tipo}</Badge>
                                      <span className="flex-1 text-muted-foreground">{m.descricao}</span>
                                      <span className="font-mono text-[10px] text-muted-foreground">{new Date(m.data).toLocaleDateString("pt-BR")}</span>
                                      <Button size="icon" variant="ghost" className="h-5 w-5" onClick={() => delMovimento(m.id)}><X className="h-3 w-3" /></Button>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </TabsContent>

                            <TabsContent value="audiencias" className="mt-2">
                              <div className="mb-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
                                <Input type="datetime-local" value={audForm.data} onChange={(e) => setAudForm(s => ({ ...s, data: e.target.value }))} className="h-8 text-xs" />
                                <Select value={audForm.tipo} onValueChange={(v) => setAudForm(s => ({ ...s, tipo: v }))}>
                                  <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                                  <SelectContent>{Object.entries(TIPO_AUD_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
                                </Select>
                                <Input value={audForm.local} onChange={(e) => setAudForm(s => ({ ...s, local: e.target.value }))} placeholder="Local" className="h-8 text-xs" />
                                <Input value={audForm.orgao} onChange={(e) => setAudForm(s => ({ ...s, orgao: e.target.value }))} placeholder="Vara/Órgão" className="h-8 text-xs" />
                                <Input value={audForm.observacoes} onChange={(e) => setAudForm(s => ({ ...s, observacoes: e.target.value }))} placeholder="Observações" className="h-8 text-xs" />
                                <Button size="sm" onClick={addAudiencia} disabled={!audForm.data}>Agendar</Button>
                              </div>
                              {audiencias.length === 0 ? (
                                <p className="py-3 text-center text-xs text-muted-foreground">Nenhuma audiência.</p>
                              ) : (
                                <div className="space-y-1.5 max-h-48 overflow-y-auto scrollbar-juridia">
                                  {audiencias.map((a) => (
                                    <div key={a.id} className="flex items-center gap-2 rounded border border-border p-2 text-xs">
                                      <Calendar className="h-3 w-3 text-primary" />
                                      <Badge variant="secondary" className="text-[10px]">{TIPO_AUD_LABELS[a.tipo] || a.tipo}</Badge>
                                      <span className="font-mono text-[10px] text-primary">{new Date(a.data).toLocaleString("pt-BR")}</span>
                                      {a.local && <span className="text-muted-foreground">{a.local}</span>}
                                      {a.orgao && <span className="text-muted-foreground">{a.orgao}</span>}
                                      <Badge variant="outline" className={`text-[10px] ${a.status === "realizada" ? "text-green-600" : a.status === "cancelada" ? "text-red-600" : ""}`}>{a.status}</Badge>
                                      {a.resultado && <span className="text-[10px] text-muted-foreground">→ {a.resultado}</span>}
                                      <Button size="icon" variant="ghost" className="h-5 w-5 ml-auto" onClick={() => delAudiencia(a.id)}><X className="h-3 w-3" /></Button>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </TabsContent>
                          </Tabs>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
