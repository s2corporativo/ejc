// ── src/components/SociedadesCliente.tsx ─────────────────────────────────────
// Seção especial do ramo Empresarial (padrão AmbientalAutos/BancarioForense):
// sociedades dos clientes via backend /empresarial/sociedades — cadastro com
// filtro por cliente, detalhe com cap table visual (barras de percentual por
// sócio, badge de administrador, alerta dourado de divergência) e linha do
// tempo de eventos societários. Documento do sócio é opcional e tratado sob
// LGPD: armazenado cifrado no backend, exibido sempre mascarado.
import { useEffect, useState } from "react";
import {
  Building2,
  Users,
  UserPlus,
  UserMinus,
  Crown,
  AlertTriangle,
  Trash2,
  Plus,
  FileText,
  TrendingUp,
  TrendingDown,
  Banknote,
  ScrollText,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import api from "../lib/api";
import { toast } from "./Toast";
import { Modal, Spinner, Empty } from "./UI";
import type { Client } from "../types";
import { asList } from "../lib/list";

// ── Tipos do contrato /empresarial/sociedades ────────────────────────────────
interface Sociedade {
  id: string;
  client_id: string;
  client_nome: string;
  razao_social: string;
  cnpj: string | null;
  tipo_societario: string;
  capital_social: number | string | null;
  socios_count: number;
}

interface Socio {
  id: string;
  nome: string;
  documento_mascarado: string | null;
  quotas: number;
  percentual: number | string;
  pro_labore: number | string | null;
  administrador: boolean;
}

interface CapTable {
  total_quotas: number;
  capital_social: number | string | null;
  alerta_percentual?: string | null;
}

interface EventoSocietario {
  id?: string;
  tipo: string;
  descricao: string;
  data_evento: string;
}

interface SociedadeDetalhe extends Sociedade {
  socios: Socio[];
  cap_table: CapTable | null;
  eventos: EventoSocietario[];
}

const PAGE_SIZE = 20; // page_size padrão do backend

const TIPOS_SOCIETARIOS = ["LTDA", "SA", "SLU", "SS", "outro"];

const EVENTO_TIPOS = [
  "constituicao",
  "alteracao_contratual",
  "entrada_socio",
  "saida_socio",
  "aumento_capital",
  "reducao_capital",
  "distribuicao_lucros",
  "assembleia",
  "outro",
];

const EVENTO_ICONE: Record<string, any> = {
  constituicao: Building2,
  alteracao_contratual: FileText,
  entrada_socio: UserPlus,
  saida_socio: UserMinus,
  aumento_capital: TrendingUp,
  reducao_capital: TrendingDown,
  distribuicao_lucros: Banknote,
  assembleia: Users,
  outro: ScrollText,
};

const FORM_SOCIEDADE_VAZIO = {
  client_id: "",
  razao_social: "",
  tipo_societario: "LTDA",
  cnpj: "",
  capital_social: "",
};

const FORM_SOCIO_VAZIO = {
  nome: "",
  documento: "",
  quotas: "",
  pro_labore: "",
  administrador: false,
};

const FORM_EVENTO_VAZIO = {
  tipo: "alteracao_contratual",
  descricao: "",
  data_evento: "",
};

function rotulo(v: string) {
  return v.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function fmtBRL(v: number | string | null | undefined) {
  const n = Number(v);
  if (v == null || v === "" || isNaN(n)) return "—";
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

/** Datas do backend vêm como "YYYY-MM-DD" — formata sem shift de timezone. */
function fmtDia(d: string | null | undefined) {
  if (!d) return "—";
  const [iso] = d.split("T");
  const partes = iso.split("-");
  return partes.length === 3 ? partes.reverse().join("/") : d;
}

function nomeCliente(c: Client) {
  return c.nome || c.razao_social || c.cnpj || c.cpf || c.id;
}

export default function SociedadesCliente() {
  // Lista + filtro
  const [clientes, setClientes] = useState<Client[]>([]);
  const [filtroCliente, setFiltroCliente] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [lista, setLista] = useState<Sociedade[] | null>(null);

  // Detalhe
  const [selId, setSelId] = useState<string | null>(null);
  const [detalhe, setDetalhe] = useState<SociedadeDetalhe | null>(null);
  const [loadingDet, setLoadingDet] = useState(false);

  // Formulários
  const [modalNova, setModalNova] = useState(false);
  const [formSoc, setFormSoc] = useState({ ...FORM_SOCIEDADE_VAZIO });
  const [salvandoSoc, setSalvandoSoc] = useState(false);
  const [formSocio, setFormSocio] = useState({ ...FORM_SOCIO_VAZIO });
  const [salvandoSocio, setSalvandoSocio] = useState(false);
  const [formEvento, setFormEvento] = useState({ ...FORM_EVENTO_VAZIO });
  const [salvandoEvento, setSalvandoEvento] = useState(false);

  useEffect(() => {
    api
      .get("/clients/", { params: { page_size: 100 } })
      .then((r) => setClientes(asList<Client>(r.data)))
      .catch(() => setClientes([]));
  }, []);

  const loadLista = () => {
    api
      .get("/empresarial/sociedades", {
        params: { client_id: filtroCliente || undefined, page },
      })
      .then((r) => {
        setLista(asList<Sociedade>(r.data));
        setTotal(r.data?.total ?? 0);
      })
      .catch(() => {
        setLista([]);
        setTotal(0);
      });
  };
  useEffect(loadLista, [filtroCliente, page]);

  const loadDetalhe = (id: string) => {
    setLoadingDet(true);
    api
      .get(`/empresarial/sociedades/${id}`)
      .then((r) => setDetalhe(r.data))
      .catch((e) => {
        toast.error(
          e.response?.data?.detail || "Erro ao carregar a sociedade.",
        );
        setDetalhe(null);
        setSelId(null);
      })
      .finally(() => setLoadingDet(false));
  };
  useEffect(() => {
    if (selId) loadDetalhe(selId);
    else setDetalhe(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selId]);

  const recarregar = () => {
    loadLista();
    if (selId) loadDetalhe(selId);
  };

  // ── Ações ──────────────────────────────────────────────────────────────
  const criarSociedade = async () => {
    if (!formSoc.client_id) {
      toast.error("Selecione o cliente.");
      return;
    }
    if (!formSoc.razao_social.trim()) {
      toast.error("Informe a razão social.");
      return;
    }
    if (!formSoc.capital_social) {
      toast.error("Informe o capital social.");
      return;
    }
    setSalvandoSoc(true);
    try {
      const payload: Record<string, unknown> = {
        client_id: formSoc.client_id,
        razao_social: formSoc.razao_social.trim(),
        tipo_societario: formSoc.tipo_societario,
        capital_social: Number(formSoc.capital_social),
      };
      if (formSoc.cnpj.trim()) payload.cnpj = formSoc.cnpj.trim();
      const r = await api.post("/empresarial/sociedades", payload);
      toast.success("Sociedade registrada.");
      setModalNova(false);
      setFormSoc({ ...FORM_SOCIEDADE_VAZIO });
      loadLista();
      if (r.data?.id) setSelId(r.data.id);
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro ao registrar sociedade.");
    } finally {
      setSalvandoSoc(false);
    }
  };

  const adicionarSocio = async () => {
    if (!detalhe) return;
    if (!formSocio.nome.trim()) {
      toast.error("Informe o nome do sócio.");
      return;
    }
    if (!formSocio.quotas || Number(formSocio.quotas) <= 0) {
      toast.error("Informe o número de quotas.");
      return;
    }
    setSalvandoSocio(true);
    try {
      const payload: Record<string, unknown> = {
        nome: formSocio.nome.trim(),
        quotas: Number(formSocio.quotas),
        administrador: formSocio.administrador,
      };
      if (formSocio.documento.trim())
        payload.documento = formSocio.documento.trim();
      if (formSocio.pro_labore)
        payload.pro_labore = Number(formSocio.pro_labore);
      await api.post(`/empresarial/sociedades/${detalhe.id}/socios`, payload);
      toast.success("Sócio adicionado.");
      setFormSocio({ ...FORM_SOCIO_VAZIO });
      recarregar();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro ao adicionar sócio.");
    } finally {
      setSalvandoSocio(false);
    }
  };

  const removerSocio = async (socioId: string) => {
    if (!window.confirm("Remover este sócio do quadro societário?")) return;
    try {
      await api.delete(`/empresarial/sociedades/socios/${socioId}`);
      toast.success("Sócio removido.");
      recarregar();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro ao remover sócio.");
    }
  };

  const adicionarEvento = async () => {
    if (!detalhe) return;
    if (!formEvento.descricao.trim()) {
      toast.error("Descreva o evento societário.");
      return;
    }
    if (!formEvento.data_evento) {
      toast.error("Informe a data do evento.");
      return;
    }
    setSalvandoEvento(true);
    try {
      await api.post(`/empresarial/sociedades/${detalhe.id}/eventos`, {
        tipo: formEvento.tipo,
        descricao: formEvento.descricao.trim(),
        data_evento: formEvento.data_evento,
      });
      toast.success("Evento registrado.");
      setFormEvento({ ...FORM_EVENTO_VAZIO });
      recarregar();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro ao registrar evento.");
    } finally {
      setSalvandoEvento(false);
    }
  };

  const totalPaginas = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div
      id="sociedades-cliente"
      className="card p-4 mb-4 border-l-4 border-warn-500 scroll-mt-4"
    >
      <div className="flex flex-wrap items-center gap-2 mb-1">
        <h2 className="font-serif font-semibold text-navy flex items-center gap-2">
          <Building2 size={16} className="text-gold-600" /> Sociedades do
          Cliente
        </h2>
        <button
          className="btn-gold text-sm ml-auto flex items-center gap-1"
          onClick={() => setModalNova(true)}
        >
          <Plus size={14} /> Nova sociedade
        </button>
      </div>
      <p className="text-xs text-slate-500 mb-4">
        Quadro societário dos clientes: cap table por sócio, administradores e
        linha do tempo de eventos societários — base para holdings, acordos de
        sócios e apuração de haveres.
      </p>

      {/* Filtro por cliente */}
      <div className="flex flex-wrap items-end gap-2 mb-3">
        <div className="flex-1 min-w-[220px]">
          <label className="label text-xs">Filtrar por cliente</label>
          <select
            className="input text-sm"
            value={filtroCliente}
            onChange={(e) => {
              setFiltroCliente(e.target.value);
              setPage(1);
              setSelId(null);
            }}
          >
            <option value="">Todos os clientes</option>
            {clientes.map((c) => (
              <option key={c.id} value={c.id}>
                {nomeCliente(c)}
              </option>
            ))}
          </select>
        </div>
        {total > 0 && (
          <span className="text-xs text-slate-400 pb-2">
            {total} sociedade(s)
          </span>
        )}
      </div>

      {/* Listagem */}
      {lista === null ? (
        <Spinner />
      ) : lista.length === 0 ? (
        <Empty message="Nenhuma sociedade registrada" />
      ) : (
        <div className="space-y-2">
          {lista.map((s) => (
            <button
              key={s.id}
              onClick={() => setSelId(selId === s.id ? null : s.id)}
              className={`w-full text-left flex flex-wrap items-center gap-3 p-3 rounded-lg border transition-colors ${
                selId === s.id
                  ? "border-gold-400 bg-gold-50/40"
                  : "border-slate-200 hover:border-gold-400"
              }`}
            >
              <div className="flex-1 min-w-[200px]">
                <div className="text-sm font-medium text-navy">
                  {s.razao_social}
                </div>
                <div className="text-xs text-slate-400">
                  {s.client_nome} · {s.cnpj || "CNPJ não informado"}
                </div>
              </div>
              <span className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
                {rotulo(s.tipo_societario)}
              </span>
              <div className="text-right">
                <div className="text-xs font-semibold text-navy">
                  {fmtBRL(s.capital_social)}
                </div>
                <div className="text-[10px] text-slate-400">
                  {s.socios_count} sócio(s)
                </div>
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Paginação */}
      {total > PAGE_SIZE && (
        <div className="flex items-center justify-end gap-2 mt-2 text-xs text-slate-500">
          <button
            className="btn-ghost text-xs flex items-center gap-1"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            <ChevronLeft size={12} /> Anterior
          </button>
          <span>
            Página {page} de {totalPaginas}
          </span>
          <button
            className="btn-ghost text-xs flex items-center gap-1"
            disabled={page >= totalPaginas}
            onClick={() => setPage((p) => p + 1)}
          >
            Próxima <ChevronRight size={12} />
          </button>
        </div>
      )}

      {/* ── Detalhe: cap table + eventos ─────────────────────────────────── */}
      {selId && (
        <div className="mt-4 pt-4 border-t border-slate-200">
          {loadingDet || !detalhe ? (
            <Spinner />
          ) : (
            <div className="grid lg:grid-cols-2 gap-4">
              {/* Cap table */}
              <div>
                <h3 className="font-serif font-semibold text-navy text-sm mb-1 flex items-center gap-2">
                  <Users size={14} className="text-gold-600" /> Cap table —{" "}
                  {detalhe.razao_social}
                </h3>
                <p className="text-[11px] text-slate-400 mb-2">
                  Capital social {fmtBRL(detalhe.cap_table?.capital_social)} ·{" "}
                  {detalhe.cap_table?.total_quotas ?? 0} quotas totais
                </p>

                {detalhe.cap_table?.alerta_percentual && (
                  <div className="mb-2 p-2 rounded-lg bg-gold-50 border border-gold-200 flex items-start gap-2 text-xs text-gold-700">
                    <AlertTriangle size={14} className="shrink-0 mt-0.5" />
                    <span>{detalhe.cap_table.alerta_percentual}</span>
                  </div>
                )}

                {detalhe.socios.length === 0 ? (
                  <Empty message="Nenhum sócio cadastrado" />
                ) : (
                  <div className="space-y-2">
                    {(Array.isArray(detalhe?.socios) ? detalhe.socios : []).map((s) => {
                      const pct = Number(s.percentual) || 0;
                      return (
                        <div
                          key={s.id}
                          className="p-2 rounded-lg border border-slate-200"
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-medium text-navy">
                              {s.nome}
                            </span>
                            {s.administrador && (
                              <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-gold-100 text-gold-700">
                                <Crown size={10} /> Administrador
                              </span>
                            )}
                            <span className="ml-auto text-xs font-semibold text-navy">
                              {pct.toFixed(2)}%
                            </span>
                            <button
                              className="text-slate-300 hover:text-danger-600"
                              title="Remover sócio"
                              onClick={() => removerSocio(s.id)}
                            >
                              <Trash2 size={13} />
                            </button>
                          </div>
                          <div className="h-2 rounded-full bg-slate-100 overflow-hidden mt-1.5">
                            <div
                              className="h-full bg-gold-600 rounded-full"
                              style={{
                                width: `${Math.min(100, Math.max(0, pct))}%`,
                              }}
                            />
                          </div>
                          <div className="text-[10px] text-slate-400 mt-1">
                            {s.quotas} quota(s)
                            {s.documento_mascarado &&
                              ` · doc. ${s.documento_mascarado}`}
                            {s.pro_labore != null &&
                              s.pro_labore !== "" &&
                              ` · pró-labore ${fmtBRL(s.pro_labore)}`}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Form novo sócio */}
                <div className="mt-3 p-3 rounded-lg bg-slate-50 border border-slate-100">
                  <p className="text-xs font-semibold text-slate-500 uppercase mb-2">
                    Adicionar sócio
                  </p>
                  <div className="grid sm:grid-cols-2 gap-2">
                    <div className="sm:col-span-2">
                      <label className="label text-xs">Nome *</label>
                      <input
                        className="input text-sm"
                        value={formSocio.nome}
                        onChange={(e) =>
                          setFormSocio({ ...formSocio, nome: e.target.value })
                        }
                      />
                    </div>
                    <div>
                      <label className="label text-xs">
                        Documento (CPF/CNPJ)
                      </label>
                      <input
                        className="input text-sm"
                        placeholder="opcional"
                        value={formSocio.documento}
                        onChange={(e) =>
                          setFormSocio({
                            ...formSocio,
                            documento: e.target.value,
                          })
                        }
                      />
                      <p className="text-[10px] text-slate-400 mt-0.5">
                        LGPD: armazenado cifrado, exibido mascarado.
                      </p>
                    </div>
                    <div>
                      <label className="label text-xs">Quotas *</label>
                      <input
                        className="input text-sm"
                        type="number"
                        value={formSocio.quotas}
                        onChange={(e) =>
                          setFormSocio({ ...formSocio, quotas: e.target.value })
                        }
                      />
                    </div>
                    <div>
                      <label className="label text-xs">Pró-labore (R$)</label>
                      <input
                        className="input text-sm"
                        type="number"
                        step="0.01"
                        value={formSocio.pro_labore}
                        onChange={(e) =>
                          setFormSocio({
                            ...formSocio,
                            pro_labore: e.target.value,
                          })
                        }
                      />
                    </div>
                    <label className="flex items-center gap-2 text-sm text-slate-600 mt-5">
                      <input
                        type="checkbox"
                        checked={formSocio.administrador}
                        onChange={(e) =>
                          setFormSocio({
                            ...formSocio,
                            administrador: e.target.checked,
                          })
                        }
                      />
                      Administrador
                    </label>
                  </div>
                  <button
                    className="btn-secondary text-xs mt-2"
                    disabled={salvandoSocio}
                    onClick={adicionarSocio}
                  >
                    {salvandoSocio ? "Adicionando…" : "Adicionar sócio"}
                  </button>
                </div>
              </div>

              {/* Linha do tempo de eventos */}
              <div>
                <h3 className="font-serif font-semibold text-navy text-sm mb-2 flex items-center gap-2">
                  <ScrollText size={14} className="text-gold-600" /> Eventos
                  societários
                </h3>
                {detalhe.eventos.length === 0 ? (
                  <Empty message="Nenhum evento registrado" />
                ) : (
                  <div className="relative pl-5 border-l-2 border-gold-200 space-y-3">
                    {detalhe.eventos.map((ev, i) => {
                      const Icone = EVENTO_ICONE[ev.tipo] || ScrollText;
                      return (
                        <div key={ev.id || i} className="relative">
                          <span className="absolute -left-[27px] top-0 w-5 h-5 rounded-full bg-gold-50 border border-gold-300 flex items-center justify-center">
                            <Icone size={11} className="text-gold-700" />
                          </span>
                          <div className="text-xs text-slate-400">
                            {fmtDia(ev.data_evento)} ·{" "}
                            <span className="font-semibold text-gold-700">
                              {rotulo(ev.tipo)}
                            </span>
                          </div>
                          <div className="text-sm text-slate-700">
                            {ev.descricao}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Form novo evento */}
                <div className="mt-3 p-3 rounded-lg bg-slate-50 border border-slate-100">
                  <p className="text-xs font-semibold text-slate-500 uppercase mb-2">
                    Registrar evento
                  </p>
                  <div className="grid sm:grid-cols-2 gap-2">
                    <div>
                      <label className="label text-xs">Tipo</label>
                      <select
                        className="input text-sm"
                        value={formEvento.tipo}
                        onChange={(e) =>
                          setFormEvento({ ...formEvento, tipo: e.target.value })
                        }
                      >
                        {EVENTO_TIPOS.map((t) => (
                          <option key={t} value={t}>
                            {rotulo(t)}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="label text-xs">Data *</label>
                      <input
                        className="input text-sm"
                        type="date"
                        value={formEvento.data_evento}
                        onChange={(e) =>
                          setFormEvento({
                            ...formEvento,
                            data_evento: e.target.value,
                          })
                        }
                      />
                    </div>
                    <div className="sm:col-span-2">
                      <label className="label text-xs">Descrição *</label>
                      <textarea
                        className="input text-sm"
                        rows={2}
                        placeholder="ex: 3ª alteração contratual — aumento de capital para R$ 500.000"
                        value={formEvento.descricao}
                        onChange={(e) =>
                          setFormEvento({
                            ...formEvento,
                            descricao: e.target.value,
                          })
                        }
                      />
                    </div>
                  </div>
                  <button
                    className="btn-secondary text-xs mt-2"
                    disabled={salvandoEvento}
                    onClick={adicionarEvento}
                  >
                    {salvandoEvento ? "Registrando…" : "Registrar evento"}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Modal: nova sociedade ─────────────────────────────────────────── */}
      <Modal
        open={modalNova}
        onClose={() => setModalNova(false)}
        title="Nova sociedade do cliente"
      >
        <div className="grid sm:grid-cols-2 gap-4">
          <div className="sm:col-span-2">
            <label className="label">Cliente *</label>
            <select
              className="input"
              value={formSoc.client_id}
              onChange={(e) =>
                setFormSoc({ ...formSoc, client_id: e.target.value })
              }
            >
              <option value="">Selecione o cliente…</option>
              {clientes.map((c) => (
                <option key={c.id} value={c.id}>
                  {nomeCliente(c)}
                </option>
              ))}
            </select>
          </div>
          <div className="sm:col-span-2">
            <label className="label">Razão social *</label>
            <input
              className="input"
              value={formSoc.razao_social}
              onChange={(e) =>
                setFormSoc({ ...formSoc, razao_social: e.target.value })
              }
            />
          </div>
          <div>
            <label className="label">Tipo societário *</label>
            <select
              className="input"
              value={formSoc.tipo_societario}
              onChange={(e) =>
                setFormSoc({ ...formSoc, tipo_societario: e.target.value })
              }
            >
              {TIPOS_SOCIETARIOS.map((t) => (
                <option key={t} value={t}>
                  {rotulo(t)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">CNPJ</label>
            <input
              className="input"
              placeholder="00.000.000/0001-00 (opcional)"
              value={formSoc.cnpj}
              onChange={(e) => setFormSoc({ ...formSoc, cnpj: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Capital social (R$) *</label>
            <input
              className="input"
              type="number"
              step="0.01"
              value={formSoc.capital_social}
              onChange={(e) =>
                setFormSoc({ ...formSoc, capital_social: e.target.value })
              }
            />
          </div>
        </div>
        <div className="flex justify-end mt-5">
          <button
            className="btn-primary"
            disabled={salvandoSoc}
            onClick={criarSociedade}
          >
            {salvandoSoc ? "Salvando…" : "Registrar sociedade"}
          </button>
        </div>
      </Modal>
    </div>
  );
}
