import { useState, useEffect, useCallback } from "react";
import {
  Plus,
  X,
  Phone,
  Mail,
  MessageCircle,
  ChevronRight,
  User,
} from "lucide-react";
import api from "../lib/api";
import { toast } from "../components/Toast";
import { soDigitos } from "../utils/phone";
import {
  Modal,
  Button,
  PageHeader,
  Spinner,
  ErrorState,
} from "../components/UI";
import { asList } from "../lib/list";

interface Lead {
  id: string;
  nome: string;
  telefone?: string;
  email?: string;
  whatsapp?: string;
  observacoes?: string;
  etapa_funil?: string;
  area_interesse?: string;
  origem_lead?: string;
  status: string;
  created_at: string;
}

const FUNIL: { key: string; label: string; topColor: string; bg: string }[] = [
  { key: "lead", label: "Lead", topColor: "border-t-slate-400", bg: "" },
  {
    key: "contato",
    label: "Contato feito",
    topColor: "border-t-primary-400",
    bg: "",
  },
  { key: "reuniao", label: "Reunião", topColor: "border-t-warn-400", bg: "" },
  {
    key: "proposta",
    label: "Proposta",
    topColor: "border-t-ai-400",
    bg: "",
  },
  {
    key: "convertido",
    label: "Convertido",
    topColor: "border-t-success-400",
    bg: "",
  },
  { key: "perdido", label: "Perdido", topColor: "border-t-danger-400", bg: "" },
];

const AREAS = [
  "Civil",
  "Trabalhista",
  "Criminal",
  "Tributário",
  "Família",
  "Empresarial",
  "Outro",
];
const ORIGENS = [
  "Indicação",
  "Instagram",
  "Site",
  "Google",
  "LinkedIn",
  "WhatsApp",
  "Outro",
];

interface FormState {
  nome: string;
  telefone: string;
  email: string;
  area_interesse: string;
  origem_lead: string;
  observacoes: string;
}
const EMPTY_FORM: FormState = {
  nome: "",
  telefone: "",
  email: "",
  area_interesse: "",
  origem_lead: "Indicação",
  observacoes: "",
};

export default function CRMLeads() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<FormState>({ ...EMPTY_FORM });
  const [dragId, setDragId] = useState<string | null>(null);
  const [overCol, setOverCol] = useState<string | null>(null);
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const res = await api.get("/clients/?page_size=500&status=lead");
      const all: Lead[] = asList<Lead>(res.data);
      setLeads(all);
    } catch {
      setLeads([]);
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function save() {
    try {
      await api.post("/clients/", {
        nome: form.nome,
        telefone: form.telefone || undefined,
        email: form.email || undefined,
        area_interesse: form.area_interesse || undefined,
        origem_lead: form.origem_lead || undefined,
        observacoes: form.observacoes || undefined,
        status: "lead",
        etapa_funil: "lead",
      });
      setShowForm(false);
      setForm({ ...EMPTY_FORM });
      load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Falha ao salvar o lead");
    }
  }

  async function mover(leadId: string, novaEtapa: string) {
    setOverCol(null);
    setLeads((prev) =>
      prev.map((l) => (l.id === leadId ? { ...l, etapa_funil: novaEtapa } : l)),
    );
    // If converted, also update status
    const extraPayload = novaEtapa === "convertido" ? { status: "aberto" } : {};
    try {
      await api.patch(`/clients/${leadId}`, {
        etapa_funil: novaEtapa,
        ...extraPayload,
      });
      if (novaEtapa === "convertido") load(); // reload to remove from leads list
    } catch (e: any) {
      toast.error(
        e?.response?.data?.detail ||
          "Falha ao mover o lead. A etapa anterior foi restaurada.",
      );
      load();
    }
  }

  function openWhatsApp(phone: string, nome: string) {
    const digits = soDigitos(phone);
    const wa = digits.startsWith("55") ? digits : "55" + digits;
    window.open(
      `https://wa.me/${wa}?text=${encodeURIComponent("Olá " + nome + ", tudo bem?")}`,
      "_blank",
    );
  }

  const convertidos = leads.filter(
    (l) => l.etapa_funil === "convertido",
  ).length;
  const taxa =
    leads.length > 0 ? Math.round((convertidos / leads.length) * 100) : 0;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 pt-6 pb-3 flex-shrink-0">
        <PageHeader
          title="CRM — Funil de Leads"
          subtitle={`${leads.length} leads · ${convertidos} convertidos · Taxa ${taxa}%`}
          actions={
            <button onClick={() => setShowForm(true)} className="btn-primary">
              <Plus className="w-4 h-4" /> Novo Lead
            </button>
          }
        />
      </div>

      {loading ? (
        <div className="flex-1 flex items-center justify-center">
          <Spinner />
        </div>
      ) : error ? (
        <div className="flex-1 flex items-center justify-center px-6 pb-6">
          <ErrorState
            message="Não foi possível carregar os leads do funil."
            onRetry={load}
          />
        </div>
      ) : (
        <div className="flex-1 overflow-x-auto px-6 pb-6">
          <div
            className="flex gap-3 h-full"
            style={{ minWidth: `${FUNIL.length * 210}px` }}
          >
            {FUNIL.map((col) => {
              const lista = leads.filter(
                (l) => (l.etapa_funil || "lead") === col.key,
              );
              return (
                <div
                  key={col.key}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setOverCol(col.key);
                  }}
                  onDragLeave={() =>
                    setOverCol((v) => (v === col.key ? null : v))
                  }
                  onDrop={() => dragId && mover(dragId, col.key)}
                  className={`flex flex-col rounded-xl border-t-2 ${col.topColor} bg-slate-50 w-52 flex-shrink-0 ${
                    overCol === col.key
                      ? "ring-2 ring-primary-300 bg-primary-50"
                      : ""
                  }`}
                >
                  <div className="px-3 py-2.5 flex items-center justify-between border-b border-slate-200">
                    <span className="text-xs font-semibold text-slate-700">
                      {col.label}
                    </span>
                    <span className="text-[11px] font-bold text-slate-400 bg-slate-900/[0.05] rounded-full px-1.5 py-0.5 dark:bg-white/[0.07]">
                      {lista.length}
                    </span>
                  </div>
                  <div className="flex-1 overflow-y-auto p-2 space-y-2">
                    {lista.map((lead) => (
                      <div
                        key={lead.id}
                        draggable
                        onDragStart={() => setDragId(lead.id)}
                        onDragEnd={() => setDragId(null)}
                        onClick={() => setSelectedLead(lead)}
                        className={`card rounded-lg p-2.5 cursor-grab active:cursor-grabbing shadow-sm hover:shadow-md transition-shadow group ${
                          dragId === lead.id ? "opacity-50" : ""
                        }`}
                      >
                        <div className="flex items-center gap-2 mb-1.5">
                          <div className="w-6 h-6 bg-slate-100 rounded-full flex items-center justify-center flex-shrink-0">
                            <User className="w-3 h-3 text-slate-400" />
                          </div>
                          <p className="text-xs font-medium text-slate-800 truncate">
                            {lead.nome}
                          </p>
                        </div>
                        {lead.area_interesse && (
                          <span className="text-[10px] bg-primary-50 text-primary-600 px-1.5 py-0.5 rounded-full">
                            {lead.area_interesse}
                          </span>
                        )}
                        {lead.origem_lead && (
                          <p className="text-[10px] text-slate-400 mt-1">
                            {lead.origem_lead}
                          </p>
                        )}
                        <div
                          className="flex gap-1 mt-2 opacity-0 group-hover:opacity-100 transition-opacity"
                          onClick={(e) => e.stopPropagation()}
                        >
                          {(lead.whatsapp || lead.telefone) && (
                            <button
                              onClick={() =>
                                openWhatsApp(
                                  lead.whatsapp || lead.telefone!,
                                  lead.nome,
                                )
                              }
                              className="p-1 bg-green-50 text-green-600 rounded hover:bg-green-100"
                            >
                              <MessageCircle className="w-3 h-3" />
                            </button>
                          )}
                          {lead.telefone && (
                            <a
                              href={`tel:${lead.telefone}`}
                              onClick={(e) => e.stopPropagation()}
                              className="p-1 bg-primary-50 text-primary-600 rounded hover:bg-primary-100"
                            >
                              <Phone className="w-3 h-3" />
                            </a>
                          )}
                          {lead.email && (
                            <a
                              href={`mailto:${lead.email}`}
                              onClick={(e) => e.stopPropagation()}
                              className="p-1 bg-slate-50 text-slate-600 rounded hover:bg-slate-100"
                            >
                              <Mail className="w-3 h-3" />
                            </a>
                          )}
                        </div>
                        <div
                          className="mt-1.5 opacity-0 group-hover:opacity-100 transition-opacity"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <select
                            className="input w-full text-[10px] px-1.5 py-0.5 text-slate-500"
                            value={lead.etapa_funil ?? "lead"}
                            onChange={(e) => mover(lead.id, e.target.value)}
                          >
                            {FUNIL.map((f) => (
                              <option key={f.key} value={f.key}>
                                {f.label}
                              </option>
                            ))}
                          </select>
                        </div>
                      </div>
                    ))}
                    {lista.length === 0 && (
                      <div className="flex items-center justify-center h-16 text-xs text-slate-300">
                        Vazio
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Lead detail side panel */}
      {selectedLead && (
        <div
          className="fixed inset-0 bg-black/40 z-50 flex items-center justify-end"
          onClick={() => setSelectedLead(null)}
        >
          <div
            className="bg-white h-full w-96 border-l border-slate-200 shadow-float overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-5 border-b border-slate-100 flex items-center justify-between">
              <h2 className="font-semibold text-slate-800">
                {selectedLead.nome}
              </h2>
              <Button
                onClick={() => setSelectedLead(null)}
                variant="ghost"
                size="icon"
                aria-label="Fechar"
                icon={<X className="w-4 h-4" />}
              />
            </div>
            <div className="p-5 space-y-4">
              {[
                { label: "Telefone", value: selectedLead.telefone },
                { label: "E-mail", value: selectedLead.email },
                {
                  label: "Área de interesse",
                  value: selectedLead.area_interesse,
                },
                { label: "Origem", value: selectedLead.origem_lead },
                { label: "Observações", value: selectedLead.observacoes },
              ]
                .filter((x) => x.value)
                .map(({ label, value }) => (
                  <div key={label}>
                    <p className="text-xs text-slate-400 uppercase tracking-wide">
                      {label}
                    </p>
                    <p className="text-sm text-slate-800 mt-0.5">{value}</p>
                  </div>
                ))}
              <div>
                <p className="text-xs text-slate-400 uppercase tracking-wide mb-2">
                  Mover no funil
                </p>
                <div className="grid grid-cols-2 gap-2">
                  {FUNIL.filter(
                    (f) => f.key !== (selectedLead.etapa_funil ?? "lead"),
                  ).map((f) => (
                    <button
                      key={f.key}
                      onClick={() => {
                        mover(selectedLead.id, f.key);
                        setSelectedLead(null);
                      }}
                      className="btn-secondary justify-start text-left text-xs px-3 py-2 gap-1.5"
                    >
                      <ChevronRight className="w-3 h-3 text-slate-400" />{" "}
                      {f.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex gap-2 pt-2">
                {(selectedLead.whatsapp || selectedLead.telefone) && (
                  <button
                    onClick={() =>
                      openWhatsApp(
                        selectedLead.whatsapp || selectedLead.telefone!,
                        selectedLead.nome,
                      )
                    }
                    className="flex items-center gap-1.5 px-3 py-2 bg-green-500 text-white rounded-lg text-xs font-medium"
                  >
                    <MessageCircle className="w-3.5 h-3.5" /> WhatsApp
                  </button>
                )}
                {selectedLead.telefone && (
                  <a
                    href={`tel:${selectedLead.telefone}`}
                    className="flex items-center gap-1.5 px-3 py-2 bg-primary-500 text-white rounded-lg text-xs font-medium"
                  >
                    <Phone className="w-3.5 h-3.5" /> Ligar
                  </a>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* New lead modal */}
      <Modal
        open={showForm}
        onClose={() => setShowForm(false)}
        title="Novo Lead"
      >
        <div className="space-y-3">
          <input
            type="text"
            placeholder="Nome completo *"
            className="input w-full text-sm"
            value={form.nome}
            onChange={(e) => setForm({ ...form, nome: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-2">
            <input
              type="tel"
              placeholder="Telefone / WhatsApp"
              className="input text-sm"
              value={form.telefone}
              onChange={(e) => setForm({ ...form, telefone: e.target.value })}
            />
            <input
              type="email"
              placeholder="E-mail"
              className="input text-sm"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <select
              className="input text-sm"
              value={form.area_interesse}
              onChange={(e) =>
                setForm({ ...form, area_interesse: e.target.value })
              }
            >
              <option value="">Área de interesse</option>
              {AREAS.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
            <select
              className="input text-sm"
              value={form.origem_lead}
              onChange={(e) =>
                setForm({ ...form, origem_lead: e.target.value })
              }
            >
              {ORIGENS.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </div>
          <textarea
            placeholder="Observações sobre o lead"
            rows={3}
            className="input w-full text-sm resize-none"
            value={form.observacoes}
            onChange={(e) => setForm({ ...form, observacoes: e.target.value })}
          />
          <div className="pt-2 flex gap-3 justify-end">
            <button onClick={() => setShowForm(false)} className="btn-ghost">
              Cancelar
            </button>
            <button
              onClick={save}
              disabled={!form.nome.trim()}
              className="btn-primary"
            >
              Salvar Lead
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
