import { exportPdf } from "../utils/exportPdf";
import { toast } from "../components/Toast";
import { exportCsv } from "../utils/exportCsv";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  FileType2,
  Download,
  Plus,
  Search,
  LayoutGrid,
  Gavel,
  Handshake,
  FileSignature,
  Archive,
  ArchiveRestore,
  Trash2,
} from "lucide-react";
import { Link as RLink } from "react-router-dom";
import api, { aplicarExtracao } from "../lib/api";
import type { AplicarExtracaoResult, ExtracaoPayload } from "../lib/api";
import type { Case, Client, Paged, User } from "../types";
import {
  PageHeader,
  StatusBadge,
  Modal,
  ConfirmModal,
  FieldLabel,
  Textarea,
  Empty,
  Spinner,
  fmtDate,
} from "../components/UI";
import { useAuth } from "../stores/auth";
import { CasosStats } from "../components/Dashboards";
import ImportarDocumento from "../components/ImportarDocumento";
import Kanban from "./Kanban";
import { List } from "lucide-react";

// Enum CaseArea do backend (app/models/case.py). Valor = chave; rótulo em PT-BR.
const AREAS = [
  "civil",
  "trabalhista",
  "consumidor",
  "familia",
  "ambiental",
  "criminal",
  "previdenciario",
  "empresarial",
  "tributario",
];
const AREA_LABELS: Record<string, string> = {
  civil: "Cível",
  trabalhista: "Trabalhista",
  consumidor: "Consumidor",
  familia: "Família",
  ambiental: "Ambiental",
  criminal: "Criminal",
  previdenciario: "Previdenciário",
  empresarial: "Empresarial",
  tributario: "Tributário",
};

const CASE_TYPES = [
  { k: "judicial", l: "Judicial", icon: Gavel },
  { k: "extrajudicial", l: "Extrajudicial", icon: Handshake },
  { k: "consultoria", l: "Consultoria", icon: FileSignature },
];
const CASE_TYPE_LABEL: Record<string, string> = {
  judicial: "Judicial",
  extrajudicial: "Extrajudicial",
  consultoria: "Consultoria",
};
const CASE_TYPE_COLOR: Record<string, string> = {
  judicial: "bg-primary-100 text-primary-700",
  extrajudicial: "bg-warn-100 text-warn-700",
  consultoria: "bg-ai-100 text-ai-700",
};
const EXTRAJ_TYPES = [
  { k: "notificacao", l: "Notificação" },
  { k: "acordo", l: "Acordo" },
  { k: "contrato", l: "Contrato" },
  { k: "parecer", l: "Parecer" },
  { k: "due_diligence", l: "Due Diligence" },
  { k: "negociacao", l: "Negociação" },
];

// Catálogo de prescrição/decadência — espelha app/services/calc/prescricao.py.
// As chaves (k) DEVEM ser idênticas às do backend: ele recusa qualquer outra.
// Enviando { tipo_acao_prescricao: k, data_fato_prescricao } o backend calcula data_prescricao.
const PRESCRICAO: {
  grupo: string;
  itens: { k: string; nm: string; base: string }[];
}[] = [
  {
    grupo: "Cível (Código Civil)",
    itens: [
      {
        k: "civel_geral",
        nm: "Prescrição geral — pretensões pessoais (10 anos)",
        base: "CC art. 205",
      },
      {
        k: "reparacao_civil",
        nm: "Reparação civil extracontratual (3 anos)",
        base: "CC art. 206 §3º V",
      },
      {
        k: "cobranca_liquida",
        nm: "Cobrança de dívida líquida (5 anos)",
        base: "CC art. 206 §5º I",
      },
      {
        k: "honorarios_profissionais",
        nm: "Honorários de profissional liberal (5 anos)",
        base: "CC art. 206 §5º II",
      },
      {
        k: "enriquecimento_sem_causa",
        nm: "Enriquecimento sem causa (3 anos)",
        base: "CC art. 206 §3º IV",
      },
      {
        k: "seguro",
        nm: "Segurado × segurador (1 ano)",
        base: "CC art. 206 §1º II",
      },
      {
        k: "alugueis",
        nm: "Cobrança de aluguéis (3 anos)",
        base: "CC art. 206 §3º I",
      },
    ],
  },
  {
    grupo: "Consumidor (CDC)",
    itens: [
      {
        k: "cdc_reparacao_fato",
        nm: "Acidente de consumo / fato do produto (5 anos)",
        base: "CDC art. 27",
      },
      {
        k: "cdc_vicio_nao_duravel",
        nm: "Vício — produto NÃO durável (30 dias · decadência)",
        base: "CDC art. 26 I",
      },
      {
        k: "cdc_vicio_duravel",
        nm: "Vício — produto durável (90 dias · decadência)",
        base: "CDC art. 26 II",
      },
    ],
  },
  {
    grupo: "Trabalhista (CF/CLT)",
    itens: [
      {
        k: "trabalhista_quinquenal",
        nm: "Créditos trabalhistas — quinquenal (5 anos)",
        base: "CF art. 7º XXIX",
      },
      {
        k: "trabalhista_bienal",
        nm: "Créditos trabalhistas — bienal pós-contrato (2 anos)",
        base: "CLT art. 11",
      },
    ],
  },
  {
    grupo: "Tributário (CTN)",
    itens: [
      {
        k: "tributario_decadencia",
        nm: "Decadência do lançamento (5 anos · decadência)",
        base: "CTN art. 173 I",
      },
      {
        k: "tributario_prescricao",
        nm: "Prescrição da cobrança (5 anos)",
        base: "CTN art. 174",
      },
    ],
  },
];

export default function Casos() {
  const [data, setData] = useState<Paged<Case> | null>(null);
  const [clientes, setClientes] = useState<Client[]>([]);
  const [advogados, setAdvogados] = useState<User[]>([]);
  const [search, setSearch] = useState("");
  const [areaF, setAreaF] = useState("");
  const [tipoF, setTipoF] = useState("");
  // Filtro por advogado responsável/auxiliar (query param advogado_id)
  const [advogadoF, setAdvogadoF] = useState("");
  // R2 — filtro ativos/arquivados/todos + ação de desarquivar por linha
  const [arquivoF, setArquivoF] = useState<"ativos" | "arquivados" | "todos">(
    "ativos",
  );
  const [desarquivandoId, setDesarquivandoId] = useState<string | null>(null);
  // Exclusão (soft delete → Lixeira) restrita a administração/sócios
  const { user } = useAuth();
  const podeExcluir = ["superadmin", "admin", "socio"].includes(
    user?.role || "",
  );
  const [delCaso, setDelCaso] = useState<Case | null>(null);
  const [delMotivo, setDelMotivo] = useState("");
  const [delLoading, setDelLoading] = useState(false);
  const [view, setView] = useState<"lista" | "kanban">("lista");
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState<any>({
    area: "civil",
    prioridade: "media",
    case_type: "judicial",
  });
  const [salvando, setSalvando] = useState(false);
  // Preview da materialização da extração de IA (dry_run) antes de aplicar.
  const [preview, setPreview] = useState<{
    caseId: string;
    caseTitulo: string;
    extracao: ExtracaoPayload;
    result: AplicarExtracaoResult;
  } | null>(null);
  const [aplicando, setAplicando] = useState(false);

  const load = () =>
    api
      .get("/cases/", {
        params: {
          search: search || undefined,
          area: areaF || undefined,
          advogado_id: advogadoF || undefined,
          arquivo: arquivoF,
          page_size: 50,
        },
      })
      .then((r) => setData(r.data));

  const desarquivar = async (id: string) => {
    setDesarquivandoId(id);
    try {
      await api.post(`/cases/${id}/desarquivar`);
      toast.success("Caso desarquivado.");
      await load();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      toast.error(
        typeof detail === "string" ? detail : "Falha ao desarquivar o caso",
      );
    } finally {
      setDesarquivandoId(null);
    }
  };

  const excluir = async () => {
    if (!delCaso) return;
    const motivo = delMotivo.trim();
    // Backend (DELETE /cases/{id}) exige motivo com no mínimo 5 caracteres
    if (motivo.length < 5) {
      toast.error("Informe o motivo da exclusão (mínimo 5 caracteres).");
      return;
    }
    setDelLoading(true);
    try {
      await api.delete(`/cases/${delCaso.id}`, { data: { motivo } });
      toast.success("Caso excluído — reversível pela Lixeira.");
      setDelCaso(null);
      setDelMotivo("");
      await load();
    } catch (e: any) {
      if (e?.response?.status === 403) {
        toast.error("Sem permissão para excluir casos (apenas admin/sócio).");
      } else {
        const detail = e?.response?.data?.detail;
        toast.error(
          typeof detail === "string"
            ? detail
            : detail?.mensagem || "Falha ao excluir o caso",
        );
      }
    } finally {
      setDelLoading(false);
    }
  };

  useEffect(() => {
    // load() inicial fica a cargo do effect de [arquivoF] abaixo
    api
      .get("/clients/", { params: { page_size: 100 } })
      .then((r) => setClientes(r.data.data));
    // advogados p/ o seletor de responsável — falha silenciosa se o perfil não puder listar usuários
    api
      .get("/users/")
      .then((r) =>
        setAdvogados(Array.isArray(r.data) ? r.data : (r.data.data ?? [])),
      )
      .catch(() => {});
  }, []);
  useEffect(() => {
    const t = setTimeout(load, 350);
    return () => clearTimeout(t);
  }, [search, areaF, advogadoF, arquivoF]);

  const salvar = async () => {
    const cand = form._cliente_candidato;
    const temCandidato = !!(cand && (cand.nome || cand.cpf || cand.cnpj));
    if (!form.titulo || (!form.client_id && !temCandidato)) {
      toast.error(
        "Título e cliente são obrigatórios (ou importe um documento)",
      );
      return;
    }
    setSalvando(true);
    try {
      let clientId = form.client_id;
      // Importação inteligente: cria/vincula cliente por CPF/CNPJ (dedup no backend)
      if (!clientId && temCandidato) {
        const { data: cli } = await api.post("/clients/resolver", cand);
        clientId = cli.id;
      }
      // Remove campos vazios e auxiliares (_extracao/_cliente_candidato não são campos do caso)
      const payload: Record<string, any> = {};
      for (const [k, v] of Object.entries(form)) {
        if (k.startsWith("_")) continue;
        if (v !== "" && v !== null && v !== undefined) payload[k] = v;
      }
      payload.client_id = clientId;
      const { data: novo } = await api.post("/cases/", payload);
      // Captura a extração antes de limpar o form (será materializada abaixo).
      const extracao = form._extracao as ExtracaoPayload | undefined;
      setModal(false);
      setForm({ area: "civil", prioridade: "media", case_type: "judicial" });
      load();
      // Materialização EXPLÍCITA: primeiro um preview (dry_run) do que SERIA
      // aplicado; o usuário confirma ("Aplicar ao caso") ou pula. Erros são
      // visíveis (nunca engolidos) — o caso já foi criado.
      if (extracao && novo?.id) {
        try {
          const result = await aplicarExtracao(novo.id, extracao, {
            dryRun: true,
          });
          setPreview({
            caseId: novo.id,
            caseTitulo: novo.titulo || payload.titulo || "caso",
            extracao,
            result,
          });
        } catch (e: any) {
          toast.error(
            e.response?.data?.detail ||
              "Caso criado, mas não foi possível pré-visualizar os dados extraídos pela IA.",
          );
        }
      }
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  // Aplica de fato (dry_run=false) o que foi mostrado no preview.
  const aplicarPreviewNoCaso = async () => {
    if (!preview) return;
    setAplicando(true);
    try {
      const r = await aplicarExtracao(preview.caseId, preview.extracao, {
        dryRun: false,
      });
      const campos = r.campos_preenchidos.length
        ? `, campos: ${r.campos_preenchidos.join(", ")}`
        : "";
      const prazos = r.prazos_criados
        ? `, ${r.prazos_criados} prazo(s) criado(s) como rascunho a confirmar`
        : "";
      toast.success(
        `Dados aplicados ao caso: ${r.partes_criadas} parte(s), ${r.areas_criadas} área(s)${campos}${prazos}.`,
      );
      setPreview(null);
      load();
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail || "Erro ao aplicar os dados ao caso.",
      );
    } finally {
      setAplicando(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Casos e Processos"
        subtitle={`${data?.total ?? 0} casos`}
        actions={
          <div className="flex gap-2 items-center">
            <div className="flex rounded-lg border border-slate-200 overflow-hidden">
              <button
                onClick={() => setView("lista")}
                className={`flex items-center gap-1 px-3 py-1.5 text-sm ${view === "lista" ? "bg-navy text-white" : "bg-white text-slate-600 hover:bg-slate-50"}`}
              >
                <List size={15} /> Lista
              </button>
              <button
                onClick={() => setView("kanban")}
                className={`flex items-center gap-1 px-3 py-1.5 text-sm ${view === "kanban" ? "bg-navy text-white" : "bg-white text-slate-600 hover:bg-slate-50"}`}
              >
                <LayoutGrid size={15} /> Quadro
              </button>
            </div>
            <button className="btn-gold" onClick={() => setModal(true)}>
              <Plus size={16} /> Novo caso
            </button>
          </div>
        }
      />

      {view === "lista" && <CasosStats />}

      {view === "kanban" && (
        <div className="-mx-2">
          <Kanban />
        </div>
      )}
      {view === "lista" && (
        <>
          <div className="flex flex-wrap gap-3 mb-4">
            <div className="relative flex-1 min-w-[220px] max-w-md">
              <Search
                size={16}
                className="absolute left-3 top-2.5 text-slate-400"
              />
              <input
                className="input pl-9"
                placeholder="Buscar título, processo, parte..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <select
              className="input w-44"
              value={areaF}
              onChange={(e) => setAreaF(e.target.value)}
            >
              <option value="">Todas as áreas</option>
              {AREAS.map((a) => (
                <option key={a} value={a}>
                  {AREA_LABELS[a] || a}
                </option>
              ))}
            </select>
            {user?.id && (
              <button
                onClick={() =>
                  setAdvogadoF((prev) => (prev === user.id ? "" : user.id))
                }
                title="Ver somente os casos em que você é responsável ou auxiliar"
                className={`px-3 py-1.5 rounded-lg text-sm font-medium whitespace-nowrap ${
                  advogadoF === user.id
                    ? "bg-gold text-navy"
                    : "bg-white border border-slate-200 text-slate-600"
                }`}
              >
                Meus casos
              </button>
            )}
            <select
              className="input w-52"
              value={advogadoF}
              onChange={(e) => setAdvogadoF(e.target.value)}
              title="Filtrar por advogado responsável ou auxiliar"
            >
              <option value="">Todos os advogados</option>
              {advogados.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name || u.email}
                </option>
              ))}
            </select>
            <div className="flex gap-1">
              <button
                onClick={() => setTipoF("")}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium ${tipoF === "" ? "bg-navy text-white" : "bg-white border border-slate-200 text-slate-600"}`}
              >
                Todos
              </button>
              {CASE_TYPES.map((t) => (
                <button
                  key={t.k}
                  onClick={() => setTipoF(t.k)}
                  className={`flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-medium ${tipoF === t.k ? "bg-navy text-white" : "bg-white border border-slate-200 text-slate-600"}`}
                >
                  <t.icon size={13} /> {t.l}
                </button>
              ))}
            </div>
            {/* R2 — alterna entre casos ativos/arquivados/todos */}
            <div className="flex rounded-lg border border-slate-200 overflow-hidden bg-white">
              {[
                ["ativos", "Ativos", List],
                ["arquivados", "Arquivados", Archive],
                ["todos", "Todos", ArchiveRestore],
              ].map(([k, label, Icon]: any) => (
                <button
                  key={k}
                  onClick={() => setArquivoF(k)}
                  className={`flex items-center gap-1 px-3 py-1.5 text-sm font-medium ${arquivoF === k ? "bg-navy text-white" : "text-slate-600 hover:bg-slate-50"}`}
                >
                  <Icon size={13} /> {label}
                </button>
              ))}
            </div>
          </div>

          {!data ? (
            <Spinner />
          ) : data.data.length === 0 ? (
            <Empty
              message={
                arquivoF === "arquivados"
                  ? "Nenhum caso arquivado"
                  : "Nenhum caso encontrado"
              }
            />
          ) : (
            <div className="card overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-bronze-50/50 text-left">
                  <tr>
                    <th className="px-4 py-2.5 label-caps">Nº interno</th>
                    <th className="px-4 py-2.5 label-caps">Título</th>
                    <th className="px-4 py-2.5 label-caps">Área</th>
                    <th className="px-4 py-2.5 label-caps">Tipo</th>
                    <th className="px-4 py-2.5 label-caps">Status</th>
                    <th className="px-4 py-2.5 label-caps">Parte contrária</th>
                    <th className="px-4 py-2.5 label-caps">Aberto em</th>
                    {(arquivoF === "arquivados" || podeExcluir) && (
                      <th className="px-4 py-2.5 label-caps">Ações</th>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-bronze-pale/40">
                  {(tipoF
                    ? data.data.filter(
                        (c: any) => (c.case_type || "judicial") === tipoF,
                      )
                    : data.data
                  ).map((c) => (
                    <tr
                      key={c.id}
                      className="hover:bg-bronze-50/40 transition-colors"
                    >
                      <td className="px-4 py-3 font-mono text-xs text-bronze-deep font-medium tracking-tight">
                        <Link to={`/casos/${c.id}`}>{c.numero_interno}</Link>
                      </td>
                      <td
                        className="px-4 py-3 text-navy-800"
                        style={{ fontWeight: 400 }}
                      >
                        <Link to={`/casos/${c.id}`} className="hover:underline">
                          {c.titulo}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-sm text-slate-500 capitalize">
                        {AREA_LABELS[(c as any).area] || c.area}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${CASE_TYPE_COLOR[(c as any).case_type || "judicial"]}`}
                        >
                          {CASE_TYPE_LABEL[(c as any).case_type || "judicial"]}
                          {(c as any).extrajudicial_type
                            ? ` · ${EXTRAJ_TYPES.find((e) => e.k === (c as any).extrajudicial_type)?.l || ""}`
                            : ""}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge value={c.status} />
                      </td>
                      <td className="px-4 py-3 text-slate-500">
                        {c.parte_contraria || "—"}
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-400">
                        {fmtDate(c.created_at)}
                      </td>
                      {(arquivoF === "arquivados" || podeExcluir) && (
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-3">
                            {arquivoF === "arquivados" && (
                              <button
                                onClick={() => desarquivar(c.id)}
                                disabled={desarquivandoId === c.id}
                                className="flex items-center gap-1 text-xs font-medium text-primary-700 hover:underline disabled:opacity-50"
                              >
                                <ArchiveRestore size={13} />
                                {desarquivandoId === c.id
                                  ? "Desarquivando..."
                                  : "Desarquivar"}
                              </button>
                            )}
                            {podeExcluir && (
                              <button
                                onClick={() => {
                                  setDelMotivo("");
                                  setDelCaso(c);
                                }}
                                title="Excluir caso (reversível pela Lixeira)"
                                className="flex items-center gap-1 text-xs font-medium text-danger-600 hover:underline"
                              >
                                <Trash2 size={13} /> Excluir
                              </button>
                            )}
                          </div>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      <Modal
        open={modal}
        onClose={() => setModal(false)}
        title="Novo caso"
        wide
      >
        <ImportarDocumento
          onPrefill={(p) => setForm((f: any) => ({ ...f, ...p }))}
        />
        {/* ── Cliente & responsável ── */}
        <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400 border-b border-slate-100 pb-1.5 mb-3">
          Cliente & responsável
        </p>
        <div className="grid sm:grid-cols-2 gap-4 mb-5">
          <div>
            <label className="label">Cliente *</label>
            <select
              className="input"
              value={form.client_id || ""}
              onChange={(e) => setForm({ ...form, client_id: e.target.value })}
            >
              <option value="">Selecione...</option>
              {clientes.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nome || c.razao_social}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Advogado responsável</label>
            <select
              className="input"
              value={form.advogado_responsavel_id || ""}
              onChange={(e) =>
                setForm({ ...form, advogado_responsavel_id: e.target.value })
              }
            >
              <option value="">Eu mesmo (padrão)</option>
              {advogados.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name}
                  {u.oab_number ? ` — OAB ${u.oab_number}` : ""}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* ── Classificação ── */}
        <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400 border-b border-slate-100 pb-1.5 mb-3">
          Classificação
        </p>
        <div className="grid sm:grid-cols-2 gap-4 mb-5">
          <div className="sm:col-span-2">
            <label className="label">Título *</label>
            <input
              className="input"
              value={form.titulo || ""}
              onChange={(e) => setForm({ ...form, titulo: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Área *</label>
            <select
              className="input"
              value={form.area}
              onChange={(e) => setForm({ ...form, area: e.target.value })}
            >
              {AREAS.map((a) => (
                <option key={a} value={a}>
                  {AREA_LABELS[a] || a}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Prioridade</label>
            <select
              className="input"
              value={form.prioridade}
              onChange={(e) => setForm({ ...form, prioridade: e.target.value })}
            >
              <option value="baixa">Baixa</option>
              <option value="media">Média</option>
              <option value="alta">Alta</option>
              <option value="critica">Crítica</option>
            </select>
          </div>
          <div>
            <label className="label">Tipo de caso</label>
            <select
              className="input"
              value={form.case_type}
              onChange={(e) =>
                setForm({
                  ...form,
                  case_type: e.target.value,
                  extrajudicial_type:
                    e.target.value === "extrajudicial"
                      ? form.extrajudicial_type
                      : undefined,
                })
              }
            >
              {CASE_TYPES.map((t) => (
                <option key={t.k} value={t.k}>
                  {t.l}
                </option>
              ))}
            </select>
          </div>
          {form.case_type === "extrajudicial" && (
            <div>
              <label className="label">Subtipo extrajudicial</label>
              <select
                className="input"
                value={form.extrajudicial_type || ""}
                onChange={(e) =>
                  setForm({ ...form, extrajudicial_type: e.target.value })
                }
              >
                <option value="">Selecione...</option>
                {EXTRAJ_TYPES.map((t) => (
                  <option key={t.k} value={t.k}>
                    {t.l}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* ── Localização processual ── */}
        <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400 border-b border-slate-100 pb-1.5 mb-3">
          Localização processual
        </p>
        <div className="grid sm:grid-cols-2 gap-4 mb-5">
          <div>
            <label className="label">Nº do processo (se houver)</label>
            <input
              className="input"
              value={form.numero_processo || ""}
              onChange={(e) =>
                setForm({ ...form, numero_processo: e.target.value })
              }
              placeholder="0000000-00.0000.0.00.0000"
            />
          </div>
          <div>
            <label className="label">Tribunal</label>
            <input
              className="input"
              value={form.tribunal || ""}
              onChange={(e) => setForm({ ...form, tribunal: e.target.value })}
              placeholder="TJMG, TRT-3, STJ..."
            />
          </div>
          <div>
            <label className="label">Comarca</label>
            <input
              className="input"
              value={form.comarca || ""}
              onChange={(e) => setForm({ ...form, comarca: e.target.value })}
              placeholder="Betim/MG"
            />
          </div>
          <div>
            <label className="label">Vara</label>
            <input
              className="input"
              value={form.vara || ""}
              onChange={(e) => setForm({ ...form, vara: e.target.value })}
              placeholder="5ª Vara Cível"
            />
          </div>
          <div className="sm:col-span-2">
            <label className="label">Parte contrária</label>
            <input
              className="input"
              value={form.parte_contraria || ""}
              onChange={(e) =>
                setForm({ ...form, parte_contraria: e.target.value })
              }
            />
          </div>
        </div>

        {/* ── Prazo prescricional / decadencial ── */}
        <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400 border-b border-slate-100 pb-1.5 mb-3">
          Prazo prescricional / decadencial
        </p>
        <div className="grid sm:grid-cols-2 gap-4 mb-2">
          <div>
            <label className="label">Tipo de pretensão</label>
            <select
              className="input"
              value={form.tipo_acao_prescricao || ""}
              onChange={(e) =>
                setForm({ ...form, tipo_acao_prescricao: e.target.value })
              }
            >
              <option value="">Não calcular agora</option>
              {PRESCRICAO.map((g) => (
                <optgroup key={g.grupo} label={g.grupo}>
                  {g.itens.map((i) => (
                    <option key={i.k} value={i.k}>
                      {i.nm} · {i.base}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
          <div>
            <label className="label">
              Termo inicial (fato / violação / ciência)
            </label>
            <input
              className="input"
              type="date"
              value={form.data_fato_prescricao || ""}
              onChange={(e) =>
                setForm({ ...form, data_fato_prescricao: e.target.value })
              }
            />
          </div>
        </div>
        <p className="text-[11px] text-warn-800 bg-warn-50 border border-warn-200 rounded-md px-3 py-2 mb-5">
          Minuta automática (revisão obrigatória): informando o tipo + termo
          inicial, o sistema calcula a data-limite na abertura do caso.
          Suspensões e interrupções (CC arts. 197–204) e particularidades do
          caso devem ser conferidas pelo advogado.
        </p>

        {/* ── Valor & fatos ── */}
        <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400 border-b border-slate-100 pb-1.5 mb-3">
          Valor & fatos
        </p>
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label className="label">Valor da causa (R$)</label>
            <input
              className="input"
              type="number"
              value={form.valor_causa || ""}
              onChange={(e) =>
                setForm({ ...form, valor_causa: e.target.value })
              }
            />
          </div>
          <div className="sm:col-span-2">
            <label className="label">
              Descrição dos fatos (usada pela IA p/ sugerir teses)
            </label>
            <textarea
              className="input min-h-[100px]"
              value={form.descricao_fatos || ""}
              onChange={(e) =>
                setForm({ ...form, descricao_fatos: e.target.value })
              }
            />
          </div>
        </div>
        <div className="flex justify-end mt-5">
          <button className="btn-primary" disabled={salvando} onClick={salvar}>
            {salvando ? "Salvando..." : "Abrir caso"}
          </button>
        </div>
      </Modal>

      {/* Preview EXPLÍCITO da materialização da extração de IA (dry_run).
          O usuário vê o que SERÁ aplicado e confirma ou pula. */}
      <Modal
        open={!!preview}
        onClose={() => setPreview(null)}
        title="Aplicar dados extraídos ao caso"
        footer={
          <>
            <button
              className="btn-ghost"
              disabled={aplicando}
              onClick={() => setPreview(null)}
            >
              Pular
            </button>
            <button
              className="btn-primary"
              disabled={
                aplicando ||
                (preview
                  ? preview.result.partes_criadas +
                      preview.result.areas_criadas +
                      preview.result.prazos_criados +
                      preview.result.campos_preenchidos.length ===
                    0
                  : true)
              }
              onClick={aplicarPreviewNoCaso}
            >
              {aplicando ? "Aplicando..." : "Aplicar ao caso"}
            </button>
          </>
        }
      >
        {preview && (
          <div className="space-y-4">
            <p className="text-sm text-slate-600">
              A IA extraiu dados do documento importado para o caso{" "}
              <span className="font-medium text-slate-900">
                {preview.caseTitulo}
              </span>
              . Confira o que será aplicado:
            </p>
            <ul className="space-y-2 text-sm">
              <li className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
                <span className="text-slate-600">Partes a criar</span>
                <span className="font-semibold text-slate-900">
                  {preview.result.partes_criadas}
                </span>
              </li>
              <li className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
                <span className="text-slate-600">Áreas a criar</span>
                <span className="font-semibold text-slate-900">
                  {preview.result.areas_criadas}
                </span>
              </li>
              <li className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
                <div className="flex items-center justify-between">
                  <span className="text-slate-600">Campos a preencher</span>
                  <span className="font-semibold text-slate-900">
                    {preview.result.campos_preenchidos.length}
                  </span>
                </div>
                {preview.result.campos_preenchidos.length > 0 && (
                  <p className="mt-1 text-xs text-slate-500">
                    {preview.result.campos_preenchidos.join(", ")}
                  </p>
                )}
              </li>
              <li className="rounded-lg border border-amber-100 bg-amber-50 px-3 py-2">
                <div className="flex items-center justify-between">
                  <span className="text-amber-800">
                    Prazos a criar (rascunho, a confirmar)
                  </span>
                  <span className="font-semibold text-amber-900">
                    {preview.result.prazos_criados}
                  </span>
                </div>
                {preview.result.prazos_criados > 0 && (
                  <p className="mt-1 text-xs text-amber-700">
                    {preview.result.prazos_criados} prazo(s) serão criados como
                    rascunho e já passam a alertar — confira e confirme cada um
                    na tela de Prazos.
                  </p>
                )}
              </li>
            </ul>
            {preview.result.partes_criadas +
              preview.result.areas_criadas +
              preview.result.prazos_criados +
              preview.result.campos_preenchidos.length ===
              0 && (
              <p className="text-xs text-slate-500">
                Nada novo a aplicar — as partes/área/campos já estão
                preenchidos no caso.
              </p>
            )}
            {preview.result.aviso && (
              <p className="text-xs text-amber-700 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
                {preview.result.aviso}
              </p>
            )}
          </div>
        )}
      </Modal>

      {/* Exclusão de caso (soft delete): motivo obrigatório no backend (≥ 5 chars) */}
      <ConfirmModal
        open={!!delCaso}
        onClose={() => setDelCaso(null)}
        onConfirm={excluir}
        variant="danger"
        title="Excluir caso"
        message={`O caso "${delCaso?.titulo ?? ""}" será enviado para a Lixeira — a exclusão é reversível pela lixeira. A ação fica registrada na Auditoria com o motivo informado.`}
        confirmLabel="Excluir caso"
        loading={delLoading}
      >
        <div className="mt-3">
          <FieldLabel required>
            Motivo da exclusão (mínimo 5 caracteres)
          </FieldLabel>
          <Textarea
            value={delMotivo}
            onChange={(e) => setDelMotivo(e.target.value)}
            rows={3}
            placeholder="Ex.: caso duplicado, cadastro de teste..."
          />
        </div>
      </ConfirmModal>
    </div>
  );
}
