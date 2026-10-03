"use client";

import { useEffect, useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Users,
  FolderOpen,
  Plus,
  Trash2,
  Edit3,
  Phone,
  Mail,
  FileText,
  ChevronRight,
  ChevronDown,
  X,
  Search,
  Archive,
  CheckCircle2,
  Circle,
  Loader2,
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
import { useAppStore } from "@/lib/store";
import { toast } from "@/hooks/use-toast";

interface Client {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  document: string | null;
  notes: string | null;
  color: string;
  casesCount: number;
  documentsCount: number;
  createdAt: string;
  updatedAt: string;
}

interface CaseItem {
  id: string;
  title: string;
  number: string | null;
  area: string;
  status: string;
  notes: string | null;
  clientId: string;
  clientName: string;
  clientColor: string;
  documentsCount: number;
  createdAt: string;
  updatedAt: string;
}

const AREA_LABELS: Record<string, string> = {
  civil: "Cível",
  penal: "Penal",
  trabalhista: "Trabalhista",
  tributario: "Tributário",
  consumer: "Consumidor",
  family: "Família",
  previdenciario: "Previdenciário",
};

const AREA_COLORS: Record<string, string> = {
  civil: "bg-blue-500/10 text-blue-600",
  penal: "bg-red-500/10 text-red-600",
  trabalhista: "bg-amber-500/10 text-amber-600",
  tributario: "bg-purple-500/10 text-purple-600",
  consumer: "bg-green-500/10 text-green-600",
  family: "bg-pink-500/10 text-pink-600",
  previdenciario: "bg-cyan-500/10 text-cyan-600",
};

export function ClientsCases() {
  const { setAppTab, setCurrentDocId, setCurrentCaseId } = useAppStore();
  const [clients, setClients] = useState<Client[]>([]);
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [expandedClient, setExpandedClient] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [clientDialogOpen, setClientDialogOpen] = useState(false);
  const [caseDialogOpen, setCaseDialogOpen] = useState(false);
  const [selectedClientId, setSelectedClientId] = useState<string | null>(null);
  const [editingClient, setEditingClient] = useState<Client | null>(null);
  const [editingCase, setEditingCase] = useState<CaseItem | null>(null);

  // Form state
  const [clientForm, setClientForm] = useState({ name: "", email: "", phone: "", document: "", notes: "" });
  const [caseForm, setCaseForm] = useState({ title: "", number: "", area: "civil", notes: "" });

  async function reload() {
    setLoading(true);
    try {
      const [cRes, csRes] = await Promise.all([
        fetch("/api/clients"),
        fetch("/api/cases"),
      ]);
      const cData = await cRes.json();
      const csData = await csRes.json();
      setClients(cData.clients || []);
      setCases(csData.cases || []);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
  }, []);

  async function saveClient() {
    if (!clientForm.name.trim()) {
      toast({ title: "Nome obrigatório", variant: "destructive" });
      return;
    }
    try {
      if (editingClient) {
        await fetch("/api/clients", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: editingClient.id, ...clientForm }),
        });
        toast({ title: "Cliente atualizado" });
      } else {
        await fetch("/api/clients", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(clientForm),
        });
        toast({ title: "Cliente criado" });
      }
      setClientDialogOpen(false);
      setEditingClient(null);
      setClientForm({ name: "", email: "", phone: "", document: "", notes: "" });
      reload();
    } catch {
      toast({ title: "Erro ao salvar cliente", variant: "destructive" });
    }
  }

  async function saveCase() {
    if (!selectedClientId) {
      toast({ title: "Selecione um cliente", variant: "destructive" });
      return;
    }
    if (!caseForm.title.trim()) {
      toast({ title: "Título do caso obrigatório", variant: "destructive" });
      return;
    }
    try {
      if (editingCase) {
        await fetch("/api/cases", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: editingCase.id, ...caseForm }),
        });
        toast({ title: "Caso atualizado" });
      } else {
        await fetch("/api/cases", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ clientId: selectedClientId, ...caseForm }),
        });
        toast({ title: "Caso criado" });
      }
      setCaseDialogOpen(false);
      setEditingCase(null);
      setCaseForm({ title: "", number: "", area: "civil", notes: "" });
      reload();
    } catch {
      toast({ title: "Erro ao salvar caso", variant: "destructive" });
    }
  }

  async function deleteClient(id: string) {
    if (!confirm("Excluir este cliente e todos os seus casos?")) return;
    try {
      await fetch(`/api/clients?id=${id}`, { method: "DELETE" });
      toast({ title: "Cliente excluído" });
      reload();
    } catch {
      toast({ title: "Erro ao excluir", variant: "destructive" });
    }
  }

  async function deleteCase(id: string) {
    if (!confirm("Excluir este caso?")) return;
    try {
      await fetch(`/api/cases?id=${id}`, { method: "DELETE" });
      toast({ title: "Caso excluído" });
      reload();
    } catch {
      toast({ title: "Erro ao excluir", variant: "destructive" });
    }
  }

  async function toggleCaseStatus(c: CaseItem) {
    const newStatus = c.status === "active" ? "concluded" : "active";
    await fetch("/api/cases", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: c.id, status: newStatus }),
    });
    toast({ title: newStatus === "concluded" ? "Caso concluído" : "Caso reativado" });
    reload();
  }

  const filteredClients = useMemo(() => {
    const q = filter.toLowerCase().trim();
    if (!q) return clients;
    return clients.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        c.email?.toLowerCase().includes(q) ||
        c.document?.toLowerCase().includes(q)
    );
  }, [clients, filter]);

  const casesForClient = (clientId: string) =>
    cases.filter((c) => c.clientId === clientId);

  function openNewClient() {
    setEditingClient(null);
    setClientForm({ name: "", email: "", phone: "", document: "", notes: "" });
    setClientDialogOpen(true);
  }

  function openEditClient(c: Client) {
    setEditingClient(c);
    setClientForm({
      name: c.name,
      email: c.email || "",
      phone: c.phone || "",
      document: c.document || "",
      notes: c.notes || "",
    });
    setClientDialogOpen(true);
  }

  function openNewCase(clientId: string) {
    setSelectedClientId(clientId);
    setEditingCase(null);
    setCaseForm({ title: "", number: "", area: "civil", notes: "" });
    setCaseDialogOpen(true);
  }

  function openEditCase(c: CaseItem) {
    setSelectedClientId(c.clientId);
    setEditingCase(c);
    setCaseForm({
      title: c.title,
      number: c.number || "",
      area: c.area,
      notes: c.notes || "",
    });
    setCaseDialogOpen(true);
  }

  return (
    <div className="container-juridia py-8">
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Clientes & Casos</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Organize seu escritório: {clients.length} cliente{clients.length === 1 ? "" : "s"},{" "}
            {cases.length} caso{cases.length === 1 ? "" : "s"} ativo{cases.length === 1 ? "" : "s"}.
          </p>
        </div>
        <Dialog open={clientDialogOpen} onOpenChange={setClientDialogOpen}>
          <DialogTrigger asChild>
            <Button onClick={openNewClient}>
              <Plus className="mr-2 h-4 w-4" /> Novo cliente
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{editingClient ? "Editar cliente" : "Novo cliente"}</DialogTitle>
            </DialogHeader>
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="c-name">Nome *</Label>
                <Input id="c-name" value={clientForm.name} onChange={(e) => setClientForm((s) => ({ ...s, name: e.target.value }))} placeholder="Nome do cliente" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="c-email">E-mail</Label>
                  <Input id="c-email" type="email" value={clientForm.email} onChange={(e) => setClientForm((s) => ({ ...s, email: e.target.value }))} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="c-phone">Telefone</Label>
                  <Input id="c-phone" value={clientForm.phone} onChange={(e) => setClientForm((s) => ({ ...s, phone: e.target.value }))} placeholder="(00) 0000-0000" />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="c-doc">CPF/CNPJ</Label>
                <Input id="c-doc" value={clientForm.document} onChange={(e) => setClientForm((s) => ({ ...s, document: e.target.value }))} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="c-notes">Observações</Label>
                <Textarea id="c-notes" rows={2} value={clientForm.notes} onChange={(e) => setClientForm((s) => ({ ...s, notes: e.target.value }))} />
              </div>
              <Button onClick={saveClient} className="w-full">
                {editingClient ? "Salvar alterações" : "Criar cliente"}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* Search */}
      <div className="mb-6 relative max-w-md">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Buscar cliente por nome, email, CPF..." className="pl-9" />
      </div>

      {loading ? (
        <div className="flex h-48 items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      ) : filteredClients.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center gap-3 py-16 text-center">
            <Users className="h-12 w-12 text-muted-foreground/40" />
            <div>
              <h3 className="font-semibold">{filter ? "Nenhum cliente encontrado" : "Nenhum cliente cadastrado"}</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                {filter ? "Tente outro termo." : "Cadastre seu primeiro cliente para começar a organizar o escritório."}
              </p>
            </div>
            <Button onClick={openNewClient}>
              <Plus className="mr-2 h-4 w-4" /> Cadastrar cliente
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {filteredClients.map((c, i) => {
            const clientCases = casesForClient(c.id);
            const isExpanded = expandedClient === c.id;
            return (
              <motion.div
                key={c.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25, delay: Math.min(i * 0.03, 0.3) }}
              >
                <Card className={isExpanded ? "ring-1 ring-primary/30" : ""}>
                  <CardHeader className="pb-2">
                    <div className="flex items-start justify-between gap-3">
                      <button
                        onClick={() => setExpandedClient(isExpanded ? null : c.id)}
                        className="flex flex-1 items-center gap-3 text-left"
                      >
                        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                          <Users className="h-5 w-5" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <h3 className="font-semibold">{c.name}</h3>
                            <Badge variant="outline" className="text-[10px]">{c.casesCount} caso{c.casesCount === 1 ? "" : "s"}</Badge>
                            <Badge variant="secondary" className="text-[10px]">{c.documentsCount} minutas</Badge>
                          </div>
                          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                            {c.email && <span className="flex items-center gap-1"><Mail className="h-3 w-3" />{c.email}</span>}
                            {c.phone && <span className="flex items-center gap-1"><Phone className="h-3 w-3" />{c.phone}</span>}
                            {c.document && <span className="font-mono">{c.document}</span>}
                          </div>
                        </div>
                      </button>
                      <div className="flex items-center gap-1">
                        <Button size="icon" variant="ghost" aria-label="Editar cliente" onClick={() => openEditClient(c)}>
                          <Edit3 className="h-4 w-4" />
                        </Button>
                        <Button size="icon" variant="ghost" aria-label="Excluir cliente" onClick={() => deleteClient(c.id)}>
                          <Trash2 className="h-4 w-4" />
                        </Button>
                        {isExpanded ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
                      </div>
                    </div>
                  </CardHeader>

                  <AnimatePresence>
                    {isExpanded && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                      >
                        <CardContent className="border-t border-border pt-3">
                          {c.notes && (
                            <p className="mb-3 rounded-md border border-dashed border-border bg-secondary/30 p-2 text-xs text-muted-foreground">
                              {c.notes}
                            </p>
                          )}
                          <div className="mb-2 flex items-center justify-between">
                            <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Casos</h4>
                            <Button size="sm" variant="outline" onClick={() => openNewCase(c.id)}>
                              <Plus className="mr-1 h-3 w-3" /> Novo caso
                            </Button>
                          </div>
                          {clientCases.length === 0 ? (
                            <p className="py-4 text-center text-xs text-muted-foreground">Nenhum caso cadastrado para este cliente.</p>
                          ) : (
                            <div className="space-y-2">
                              {clientCases.map((cs) => (
                                <div
                                  key={cs.id}
                                  className={`flex items-center gap-3 rounded-lg border p-2.5 transition-colors ${
                                    cs.status === "concluded" ? "border-green-500/30 bg-green-500/5 opacity-75" : "border-border"
                                  }`}
                                >
                                  <button onClick={() => toggleCaseStatus(cs)} className="shrink-0" aria-label="Toggle status">
                                    {cs.status === "concluded" ? (
                                      <CheckCircle2 className="h-5 w-5 text-green-600" />
                                    ) : (
                                      <Circle className="h-5 w-5 text-muted-foreground" />
                                    )}
                                  </button>
                                  <div className="min-w-0 flex-1">
                                    <div className="flex items-center gap-2">
                                      <span className="truncate text-sm font-medium">{cs.title}</span>
                                      <Badge variant="outline" className={`text-[10px] ${AREA_COLORS[cs.area] || ""}`}>
                                        {AREA_LABELS[cs.area] || cs.area}
                                      </Badge>
                                      {cs.number && <span className="font-mono text-[10px] text-muted-foreground">{cs.number}</span>}
                                    </div>
                                    <div className="mt-0.5 text-[10px] text-muted-foreground">
                                      {cs.documentsCount} minuta{cs.documentsCount === 1 ? "" : "s"} · Atualizado {new Date(cs.updatedAt).toLocaleDateString("pt-BR")}
                                    </div>
                                  </div>
                                  <div className="flex gap-1">
                                    <Button size="icon" variant="ghost" aria-label="Editar caso" onClick={() => openEditCase(cs)}>
                                      <Edit3 className="h-3.5 w-3.5" />
                                    </Button>
                                    <Button size="icon" variant="ghost" aria-label="Excluir caso" onClick={() => deleteCase(cs.id)}>
                                      <Trash2 className="h-3.5 w-3.5" />
                                    </Button>
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </CardContent>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </Card>
              </motion.div>
            );
          })}
        </div>
      )}

      {/* Case Dialog */}
      <Dialog open={caseDialogOpen} onOpenChange={setCaseDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingCase ? "Editar caso" : "Novo caso"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="case-title">Título do caso *</Label>
              <Input id="case-title" value={caseForm.title} onChange={(e) => setCaseForm((s) => ({ ...s, title: e.target.value }))} placeholder="Ex: Ação indenizatória" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="case-number">Número do processo</Label>
                <Input id="case-number" value={caseForm.number} onChange={(e) => setCaseForm((s) => ({ ...s, number: e.target.value }))} placeholder="0000000-00.0000.0.00.0000" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="case-area">Área</Label>
                <Select value={caseForm.area} onValueChange={(v) => setCaseForm((s) => ({ ...s, area: v }))}>
                  <SelectTrigger id="case-area"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.entries(AREA_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="case-notes">Observações</Label>
              <Textarea id="case-notes" rows={3} value={caseForm.notes} onChange={(e) => setCaseForm((s) => ({ ...s, notes: e.target.value }))} />
            </div>
            <Button onClick={saveCase} className="w-full">
              {editingCase ? "Salvar alterações" : "Criar caso"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
