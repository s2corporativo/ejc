// ── src/pages/Ajuizamento.tsx ────────────────────────────────────────────────
// Wizard de ajuizamento: caso de origem → tribunal/sistema → classe/assuntos →
// partes (pré-preenchidas do caso) → advogados → características → petição e
// anexos → validação → REVISÃO HUMANA → assinatura/protocolo → resultado.
//
// Nenhuma regra de negócio vive aqui: cada passo chama o backend
// (/ajuizamento/*), que é a fonte da verdade do preflight, da máquina de
// estados, das capacidades e do registro do protocolo.
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  FileSignature,
  Gavel,
  ShieldCheck,
} from "lucide-react";

import api from "../lib/api";
import { asList } from "../lib/list";
import { toast } from "../components/Toast";
import {
  Alert,
  Badge,
  Button,
  EmptyState,
  ErrorState,
  FieldLabel,
  Input,
  PageHeader,
  SectionCard,
  Select,
  Spinner,
  Textarea,
  fmtDate,
} from "../components/UI";
import {
  CONFIRMACAO_REVISAO,
  ETAPAS,
  ROTULO_CAPACIDADE,
  ROTULO_ESTADO,
  SISTEMAS,
  etapaDoEstado,
  montarPayloadFiling,
  podeAprovar,
  podeAssinar,
  podeEditar,
  podeProtocolar,
  protocoloEletronicoLiberado,
  resumoCapacidade,
  type AssuntoAjuizamento,
  type DocumentoAjuizamento,
  type Filing,
} from "../lib/ajuizamento";

interface CasoResumo {
  id: string;
  numero_interno?: string;
  titulo: string;
  cliente_nome?: string;
  tribunal?: string;
  comarca?: string;
  valor_causa?: number;
}

interface ParteCaso {
  id: string;
  tipo: string;
  nome: string;
  cpf_cnpj?: string | null;
  oab?: string | null;
}

interface DocumentoCaso {
  id: string;
  titulo: string;
  filename: string;
  mimetype?: string | null;
  sha256?: string | null;
}

interface PecaCaso {
  id: string;
  titulo: string;
  status: string;
  tipo_peca: string;
}

const TIPOS_ANEXO: DocumentoAjuizamento["document_type"][] = [
  "procuracao",
  "documento_pessoal",
  "comprovante",
  "probatorio",
  "complementar",
];

function Passos({ atual, ir }: { atual: number; ir: (i: number) => void }) {
  return (
    <ol
      className="mb-6 flex flex-wrap gap-1.5"
      aria-label="Etapas do ajuizamento"
    >
      {ETAPAS.map((etapa, i) => (
        <li key={etapa}>
          <button
            type="button"
            onClick={() => ir(i)}
            aria-current={i === atual ? "step" : undefined}
            className={`rounded-lg border px-2.5 py-1 text-xs ${
              i === atual
                ? "border-primary-300 bg-primary-50 font-semibold text-primary-800"
                : "border-slate-200 bg-white text-slate-500 hover:border-primary-200"
            }`}
          >
            {i + 1}. {etapa}
          </button>
        </li>
      ))}
    </ol>
  );
}

export default function Ajuizamento() {
  const [searchParams, setSearchParams] = useSearchParams();
  const casoId = searchParams.get("caso") || "";
  const filingId = searchParams.get("filing") || "";

  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [etapa, setEtapa] = useState(0);

  const [casos, setCasos] = useState<CasoResumo[]>([]);
  const [caso, setCaso] = useState<CasoResumo | null>(null);
  const [partes, setPartes] = useState<ParteCaso[]>([]);
  const [documentos, setDocumentos] = useState<DocumentoCaso[]>([]);
  const [pecas, setPecas] = useState<PecaCaso[]>([]);
  const [filing, setFiling] = useState<Filing | null>(null);
  const [form, setForm] = useState<Partial<Filing>>({
    system: "pje_mni",
    degree: "1",
    environment: "homologacao",
    nivel_sigilo: 0,
    gratuidade: false,
    tutela: false,
    assuntos: [{ codigo: "", nome: "", principal: true }],
    documentos: [],
    advogados: [],
    caracteristicas: {},
  });
  const [confirmacao, setConfirmacao] = useState("");
  const [observacoes, setObservacoes] = useState("");
  const [assinatura, setAssinatura] = useState({
    provider: "registro_externo",
    certificate_subject: "",
    certificate_serial: "",
    signed_document_id: "",
    signed_document_hash: "",
  });
  const [manual, setManual] = useState({
    cnj_number: "",
    external_protocol: "",
    distribution_unit: "",
    receipt_document_id: "",
  });
  const [resultado, setResultado] = useState<Record<string, unknown> | null>(
    null,
  );

  // ── Carga ──────────────────────────────────────────────────────────────
  useEffect(() => {
    let vivo = true;
    api
      .get("/cases", { params: { page_size: 100 } })
      .then((r) => {
        if (vivo) setCasos(asList<CasoResumo>(r.data));
      })
      .catch(() => {
        if (vivo) setCasos([]);
      });
    return () => {
      vivo = false;
    };
  }, []);

  const carregarContexto = useCallback(async (id: string) => {
    setCarregando(true);
    setErro(null);
    try {
      const [c, p, d, pc] = await Promise.all([
        api.get(`/cases/${id}`),
        api.get(`/cases/${id}/partes`).catch(() => ({ data: [] })),
        api
          .get("/documents", { params: { case_id: id, page_size: 100 } })
          .catch(() => ({ data: [] })),
        api
          .get("/legal-docs", { params: { case_id: id } })
          .catch(() => ({ data: [] })),
      ]);
      setCaso(c.data);
      setPartes(asList<ParteCaso>(p.data));
      setDocumentos(asList<DocumentoCaso>(d.data));
      setPecas(asList<PecaCaso>(pc.data));
      setForm((f) => ({
        ...f,
        tribunal_code: f.tribunal_code || c.data?.tribunal || "",
        jurisdicao: f.jurisdicao || c.data?.comarca || "",
        valor_causa:
          f.valor_causa ??
          (c.data?.valor_causa ? String(c.data.valor_causa) : undefined),
      }));
    } catch {
      setErro("Não foi possível carregar o caso, as partes e os documentos.");
    } finally {
      setCarregando(false);
    }
  }, []);

  const carregarFiling = useCallback(
    async (id: string) => {
      setCarregando(true);
      try {
        const r = await api.get(`/ajuizamento/filings/${id}`);
        const f: Filing = r.data;
        setFiling(f);
        setForm({ ...f });
        setEtapa((e) => (e === 0 ? etapaDoEstado(f.estado) : e));
        if (f.case_id) await carregarContexto(f.case_id);
      } catch {
        setErro("Não foi possível carregar este ajuizamento.");
      } finally {
        setCarregando(false);
      }
    },
    [carregarContexto],
  );

  useEffect(() => {
    if (filingId) void carregarFiling(filingId);
    else if (casoId) void carregarContexto(casoId);
  }, [filingId, casoId, carregarFiling, carregarContexto]);

  const matriz = filing?.preflight?.matriz;
  const editavel = !filing || podeEditar(filing.estado);

  // ── Ações ──────────────────────────────────────────────────────────────
  async function salvar() {
    setSalvando(true);
    try {
      const payload = montarPayloadFiling({
        ...form,
        case_id: casoId || caso?.id,
      });
      const r = filing
        ? await api.patch(`/ajuizamento/filings/${filing.id}`, payload)
        : await api.post("/ajuizamento/filings", payload);
      setFiling(r.data);
      setForm({ ...r.data });
      if (!filing) setSearchParams({ caso: r.data.case_id, filing: r.data.id });
      toast.success("Ajuizamento salvo.");
      return r.data as Filing;
    } catch (e) {
      toast.error(mensagem(e, "Não foi possível salvar o ajuizamento."));
      return null;
    } finally {
      setSalvando(false);
    }
  }

  async function validar() {
    const atual = await salvar();
    if (!atual) return;
    setSalvando(true);
    try {
      const r = await api.post(`/ajuizamento/filings/${atual.id}/validar`);
      setFiling(r.data.filing);
      setEtapa(7);
      if (r.data.preflight?.ready)
        toast.success("Validação concluída sem bloqueios.");
      else toast.error("Há pendências que impedem o protocolo.");
    } catch (e) {
      toast.error(mensagem(e, "Falha ao validar."));
    } finally {
      setSalvando(false);
    }
  }

  async function aprovar() {
    if (!filing) return;
    setSalvando(true);
    try {
      const r = await api.post(`/ajuizamento/filings/${filing.id}/aprovar`, {
        confirmacao,
        observacoes: observacoes || undefined,
      });
      setFiling(r.data);
      setEtapa(9);
      toast.success("Revisão registrada. Ajuizamento aprovado.");
    } catch (e) {
      toast.error(mensagem(e, "Não foi possível aprovar."));
    } finally {
      setSalvando(false);
    }
  }

  async function assinar() {
    if (!filing) return;
    setSalvando(true);
    try {
      const corpo: Record<string, unknown> = { provider: assinatura.provider };
      if (assinatura.certificate_subject)
        corpo.certificate_subject = assinatura.certificate_subject;
      if (assinatura.certificate_serial)
        corpo.certificate_serial = assinatura.certificate_serial;
      if (assinatura.signed_document_id)
        corpo.signed_document_id = assinatura.signed_document_id;
      if (assinatura.signed_document_hash)
        corpo.signed_document_hash = assinatura.signed_document_hash;
      const r = await api.post(
        `/ajuizamento/filings/${filing.id}/assinar`,
        corpo,
      );
      if (r.data.estado === "SUPPORTED")
        toast.success("Assinatura registrada.");
      else toast.error(r.data.mensagem || "Assinatura não concluída.");
      await carregarFiling(filing.id);
    } catch (e) {
      toast.error(mensagem(e, "Falha ao registrar a assinatura."));
    } finally {
      setSalvando(false);
    }
  }

  async function protocolar() {
    if (!filing) return;
    setSalvando(true);
    try {
      const r = await api.post(`/ajuizamento/filings/${filing.id}/protocolar`);
      setResultado(r.data);
      setEtapa(10);
      await carregarFiling(filing.id);
    } catch (e) {
      toast.error(mensagem(e, "Falha ao protocolar."));
    } finally {
      setSalvando(false);
    }
  }

  async function confirmarManual() {
    if (!filing) return;
    setSalvando(true);
    try {
      const corpo: Record<string, unknown> = {};
      Object.entries(manual).forEach(([k, v]) => {
        if (v) corpo[k] = v;
      });
      const r = await api.post(
        `/ajuizamento/filings/${filing.id}/confirmar-manual`,
        corpo,
      );
      setResultado(r.data);
      setEtapa(10);
      toast.success("Protocolo registrado e vinculado ao caso.");
      await carregarFiling(filing.id);
    } catch (e) {
      toast.error(mensagem(e, "Não foi possível registrar o protocolo."));
    } finally {
      setSalvando(false);
    }
  }

  async function sincronizar() {
    if (!filing) return;
    setSalvando(true);
    try {
      const r = await api.post(`/ajuizamento/filings/${filing.id}/sincronizar`);
      toast.success(
        `Sincronização concluída (${r.data.movimentos_novos ?? 0} movimento(s) novo(s)).`,
      );
      await carregarFiling(filing.id);
    } catch (e) {
      toast.error(mensagem(e, "Falha ao sincronizar."));
    } finally {
      setSalvando(false);
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────
  const partesAtivas = useMemo(
    () =>
      partes.filter((p) =>
        ["autor", "requerente", "exequente"].includes(
          (p.tipo || "").toLowerCase(),
        ),
      ),
    [partes],
  );
  const partesPassivas = useMemo(
    () =>
      partes.filter((p) =>
        ["reu", "requerido", "executado"].includes(
          (p.tipo || "").toLowerCase(),
        ),
      ),
    [partes],
  );

  return (
    <div className="p-4 sm:p-6">
      <PageHeader
        eyebrow="Ajuizamento"
        title="Ajuizar ação"
        subtitle="Do caso ao protocolo, sem redigitação: validação, revisão humana e registro do protocolo."
        actions={
          <Link
            to="/ajuizamento/perfis"
            className="btn-secondary flex items-center gap-1"
          >
            <ShieldCheck className="h-4 w-4" /> Perfis de tribunal
          </Link>
        }
      />

      {erro && (
        <ErrorState
          message={erro}
          onRetry={() =>
            filingId ? carregarFiling(filingId) : carregarContexto(casoId)
          }
        />
      )}
      {carregando && (
        <div className="flex justify-center py-10">
          <Spinner />
        </div>
      )}

      {!carregando && !erro && (
        <>
          <Passos atual={etapa} ir={setEtapa} />
          {filing && (
            <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
              <Badge>{ROTULO_ESTADO[filing.estado]}</Badge>
              {filing.numero_cnj && (
                <span className="text-slate-600">
                  Processo {filing.numero_cnj}
                </span>
              )}
              {filing.ultimo_erro && (
                <span className="text-danger-600">{filing.ultimo_erro}</span>
              )}
            </div>
          )}

          {/* 1 — Caso de origem */}
          {etapa === 0 && (
            <SectionCard title="Caso de origem">
              {casos.length === 0 ? (
                <EmptyState
                  title="Nenhum caso disponível"
                  message="Cadastre um caso antes de ajuizar."
                />
              ) : (
                <>
                  <FieldLabel>Caso</FieldLabel>
                  <Select
                    value={casoId}
                    onChange={(e) =>
                      setSearchParams(
                        e.target.value ? { caso: e.target.value } : {},
                      )
                    }
                    disabled={!!filing}
                  >
                    <option value="">Selecione…</option>
                    {casos.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.numero_interno ? `${c.numero_interno} — ` : ""}
                        {c.titulo}
                      </option>
                    ))}
                  </Select>
                  {caso && (
                    <p className="mt-3 text-sm text-slate-600">
                      Cliente, partes, documentos e peças deste caso serão
                      reaproveitados — nada é redigitado.
                    </p>
                  )}
                </>
              )}
            </SectionCard>
          )}

          {/* 2 — Tribunal e sistema */}
          {etapa === 1 && (
            <SectionCard title="Tribunal e sistema">
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <FieldLabel>Tribunal (sigla)</FieldLabel>
                  <Input
                    value={form.tribunal_code || ""}
                    disabled={!editavel}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        tribunal_code: e.target.value.toUpperCase(),
                      })
                    }
                    placeholder="TJMG"
                  />
                </div>
                <div>
                  <FieldLabel>Sistema</FieldLabel>
                  <Select
                    value={form.system || ""}
                    disabled={!editavel}
                    onChange={(e) =>
                      setForm({ ...form, system: e.target.value })
                    }
                  >
                    {SISTEMAS.map((s) => (
                      <option key={s.valor} value={s.valor}>
                        {s.rotulo}
                      </option>
                    ))}
                  </Select>
                  <p className="mt-1 text-xs text-slate-500">
                    {SISTEMAS.find((s) => s.valor === form.system)?.nota}
                  </p>
                </div>
                <div>
                  <FieldLabel>Grau</FieldLabel>
                  <Select
                    value={form.degree || "1"}
                    disabled={!editavel}
                    onChange={(e) =>
                      setForm({ ...form, degree: e.target.value })
                    }
                  >
                    <option value="1">1º grau</option>
                    <option value="2">2º grau</option>
                  </Select>
                </div>
                <div>
                  <FieldLabel>Ambiente</FieldLabel>
                  <Select
                    value={form.environment || "homologacao"}
                    disabled={!editavel}
                    onChange={(e) =>
                      setForm({ ...form, environment: e.target.value })
                    }
                  >
                    <option value="homologacao">Homologação</option>
                    <option value="producao">Produção</option>
                  </Select>
                </div>
              </div>
            </SectionCard>
          )}

          {/* 3 — Classe, assuntos, jurisdição, competência */}
          {etapa === 2 && (
            <SectionCard title="Classe, assuntos, jurisdição e competência">
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <FieldLabel>Classe (código TPU)</FieldLabel>
                  <Input
                    value={form.classe_codigo || ""}
                    disabled={!editavel}
                    onChange={(e) =>
                      setForm({ ...form, classe_codigo: e.target.value })
                    }
                    placeholder="7"
                  />
                </div>
                <div>
                  <FieldLabel>Classe (descrição)</FieldLabel>
                  <Input
                    value={form.classe_nome || ""}
                    disabled={!editavel}
                    onChange={(e) =>
                      setForm({ ...form, classe_nome: e.target.value })
                    }
                  />
                </div>
                <div>
                  <FieldLabel>Jurisdição / comarca</FieldLabel>
                  <Input
                    value={form.jurisdicao || ""}
                    disabled={!editavel}
                    onChange={(e) =>
                      setForm({ ...form, jurisdicao: e.target.value })
                    }
                  />
                </div>
                <div>
                  <FieldLabel>Código da localidade</FieldLabel>
                  <Input
                    value={form.codigo_localidade || ""}
                    disabled={!editavel}
                    onChange={(e) =>
                      setForm({ ...form, codigo_localidade: e.target.value })
                    }
                    placeholder="3106705"
                  />
                </div>
                <div>
                  <FieldLabel>Competência</FieldLabel>
                  <Input
                    value={form.competencia || ""}
                    disabled={!editavel}
                    onChange={(e) =>
                      setForm({ ...form, competencia: e.target.value })
                    }
                  />
                </div>
                <div>
                  <FieldLabel>Competência (código)</FieldLabel>
                  <Input
                    value={form.competencia_codigo || ""}
                    disabled={!editavel}
                    onChange={(e) =>
                      setForm({ ...form, competencia_codigo: e.target.value })
                    }
                  />
                </div>
              </div>

              <div className="mt-4">
                <FieldLabel>Assuntos (códigos TPU)</FieldLabel>
                {(form.assuntos || []).map(
                  (a: AssuntoAjuizamento, i: number) => (
                    <div
                      key={i}
                      className="mb-2 flex flex-wrap items-center gap-2"
                    >
                      <Input
                        className="w-28"
                        value={a.codigo}
                        disabled={!editavel}
                        onChange={(e) => {
                          const lista = [...(form.assuntos || [])];
                          lista[i] = { ...lista[i], codigo: e.target.value };
                          setForm({ ...form, assuntos: lista });
                        }}
                        placeholder="10375"
                      />
                      <Input
                        value={a.nome || ""}
                        disabled={!editavel}
                        onChange={(e) => {
                          const lista = [...(form.assuntos || [])];
                          lista[i] = { ...lista[i], nome: e.target.value };
                          setForm({ ...form, assuntos: lista });
                        }}
                        placeholder="Descrição"
                      />
                      <label className="flex items-center gap-1 text-xs text-slate-600">
                        <input
                          type="radio"
                          name="assunto-principal"
                          checked={!!a.principal}
                          disabled={!editavel}
                          onChange={() => {
                            const lista = (form.assuntos || []).map((x, j) => ({
                              ...x,
                              principal: i === j,
                            }));
                            setForm({ ...form, assuntos: lista });
                          }}
                        />
                        principal
                      </label>
                    </div>
                  ),
                )}
                {editavel && (
                  <Button
                    variant="secondary"
                    onClick={() =>
                      setForm({
                        ...form,
                        assuntos: [
                          ...(form.assuntos || []),
                          { codigo: "", nome: "", principal: false },
                        ],
                      })
                    }
                  >
                    Adicionar assunto
                  </Button>
                )}
              </div>
            </SectionCard>
          )}

          {/* 4 — Partes */}
          {etapa === 3 && (
            <SectionCard title="Partes (do cadastro do caso)">
              {partes.length === 0 ? (
                <EmptyState
                  title="Sem partes cadastradas"
                  message="Cadastre autor e réu na aba Partes do caso — o ajuizamento usa exatamente esses dados."
                  action={
                    caso ? (
                      <Link
                        className="btn-secondary"
                        to={`/casos/${caso.id}?tab=partes`}
                      >
                        Abrir Partes do caso
                      </Link>
                    ) : undefined
                  }
                />
              ) : (
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <div className="mb-1 text-xs font-semibold uppercase text-slate-500">
                      Polo ativo
                    </div>
                    <ul className="text-sm text-slate-700">
                      <li>
                        {caso?.cliente_nome || "Cliente do caso"} (cliente)
                      </li>
                      {partesAtivas.map((p) => (
                        <li key={p.id}>{p.nome}</li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <div className="mb-1 text-xs font-semibold uppercase text-slate-500">
                      Polo passivo
                    </div>
                    {partesPassivas.length === 0 ? (
                      <Alert variant="warning" title="Polo passivo vazio">
                        A validação vai bloquear o protocolo sem ao menos um
                        réu.
                      </Alert>
                    ) : (
                      <ul className="text-sm text-slate-700">
                        {partesPassivas.map((p) => (
                          <li key={p.id}>{p.nome}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              )}
            </SectionCard>
          )}

          {/* 5 — Advogados */}
          {etapa === 4 && (
            <SectionCard title="Advogados e procuração">
              <p className="mb-3 text-sm text-slate-600">
                Os advogados vêm do caso (responsável e auxiliar). A OAB é lida
                do cadastro do usuário.
              </p>
              <ul className="text-sm text-slate-700">
                {(form.advogados || []).map((a) => (
                  <li key={a.user_id}>
                    {a.user_id} — {a.tipo || "advogado"}
                  </li>
                ))}
                {(form.advogados || []).length === 0 && (
                  <Alert variant="warning" title="Sem advogado vinculado">
                    Defina o advogado responsável do caso antes de validar.
                  </Alert>
                )}
              </ul>
            </SectionCard>
          )}

          {/* 6 — Características */}
          {etapa === 5 && (
            <SectionCard title="Características do processo">
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <FieldLabel>Valor da causa</FieldLabel>
                  <Input
                    value={form.valor_causa || ""}
                    disabled={!editavel}
                    onChange={(e) =>
                      setForm({ ...form, valor_causa: e.target.value })
                    }
                    placeholder="15000.00"
                  />
                </div>
                <div>
                  <FieldLabel>Nível de sigilo (0 a 5)</FieldLabel>
                  <Input
                    type="number"
                    min={0}
                    max={5}
                    value={String(form.nivel_sigilo ?? 0)}
                    disabled={!editavel}
                    onChange={(e) =>
                      setForm({ ...form, nivel_sigilo: Number(e.target.value) })
                    }
                  />
                </div>
                <label className="flex items-center gap-2 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    checked={!!form.gratuidade}
                    disabled={!editavel}
                    onChange={(e) =>
                      setForm({ ...form, gratuidade: e.target.checked })
                    }
                  />
                  Gratuidade de justiça
                </label>
                <label className="flex items-center gap-2 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    checked={!!form.tutela}
                    disabled={!editavel}
                    onChange={(e) =>
                      setForm({ ...form, tutela: e.target.checked })
                    }
                  />
                  Pedido de tutela / liminar
                </label>
              </div>
            </SectionCard>
          )}

          {/* 7 — Petição e anexos */}
          {etapa === 6 && (
            <SectionCard title="Petição inicial e anexos">
              <FieldLabel>Petição inicial (peça aprovada do caso)</FieldLabel>
              <Select
                value={form.peticao_legal_doc_id || ""}
                disabled={!editavel}
                onChange={(e) =>
                  setForm({ ...form, peticao_legal_doc_id: e.target.value })
                }
              >
                <option value="">Selecione…</option>
                {pecas.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.titulo} ({p.status})
                  </option>
                ))}
              </Select>

              <div className="mt-4">
                <FieldLabel>Anexos (documentos do caso)</FieldLabel>
                {documentos.length === 0 ? (
                  <EmptyState
                    title="Sem documentos"
                    message="Anexe documentos ao caso para juntá-los."
                  />
                ) : (
                  <ul className="space-y-2">
                    {documentos.map((d) => {
                      const sel = (form.documentos || []).find(
                        (x) => x.document_id === d.id,
                      );
                      return (
                        <li
                          key={d.id}
                          className="flex flex-wrap items-center gap-2 text-sm"
                        >
                          <input
                            type="checkbox"
                            checked={!!sel}
                            disabled={!editavel}
                            onChange={(e) => {
                              const lista = (form.documentos || []).filter(
                                (x) => x.document_id !== d.id,
                              );
                              if (e.target.checked) {
                                lista.push({
                                  document_id: d.id,
                                  document_type: "complementar",
                                  ordem: lista.length + 1,
                                });
                              }
                              setForm({ ...form, documentos: lista });
                            }}
                          />
                          <span className="min-w-0 flex-1 truncate">
                            {d.titulo || d.filename}
                          </span>
                          {sel && (
                            <Select
                              className="w-44"
                              value={sel.document_type}
                              disabled={!editavel}
                              onChange={(e) => {
                                const lista = (form.documentos || []).map(
                                  (x) =>
                                    x.document_id === d.id
                                      ? {
                                          ...x,
                                          document_type: e.target
                                            .value as DocumentoAjuizamento["document_type"],
                                        }
                                      : x,
                                );
                                setForm({ ...form, documentos: lista });
                              }}
                            >
                              {TIPOS_ANEXO.map((t) => (
                                <option key={t} value={t}>
                                  {t}
                                </option>
                              ))}
                            </Select>
                          )}
                          {!d.sha256 && (
                            <span className="text-xs text-warn-600">
                              sem hash SHA-256
                            </span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            </SectionCard>
          )}

          {/* 8 — Validação */}
          {etapa === 7 && (
            <SectionCard title="Validação (preflight)">
              {!filing?.preflight ? (
                <EmptyState
                  title="Ainda não validado"
                  message="Rode a validação para conferir partes, documentos, classe, assuntos e capacidade do conector."
                />
              ) : (
                <div className="space-y-3">
                  <Alert
                    variant={filing.preflight.ready ? "success" : "error"}
                    title={
                      filing.preflight.ready
                        ? "Pronto para revisão"
                        : "Pendências bloqueiam o protocolo"
                    }
                  >
                    {resumoCapacidade(matriz)}
                  </Alert>
                  {filing.preflight.errors.length > 0 && (
                    <ul className="list-inside list-disc text-sm text-danger-700">
                      {filing.preflight.errors.map((e) => (
                        <li key={e}>{e}</li>
                      ))}
                    </ul>
                  )}
                  {filing.preflight.warnings.length > 0 && (
                    <ul className="list-inside list-disc text-sm text-warn-700">
                      {filing.preflight.warnings.map((w) => (
                        <li key={w}>{w}</li>
                      ))}
                    </ul>
                  )}
                  {filing.preflight.authorization_requirements.length > 0 && (
                    <Alert
                      variant="warning"
                      title="Pendências de autorização externa"
                    >
                      <ul className="list-inside list-disc">
                        {filing.preflight.authorization_requirements.map(
                          (r) => (
                            <li key={r}>{r}</li>
                          ),
                        )}
                      </ul>
                    </Alert>
                  )}
                </div>
              )}
            </SectionCard>
          )}

          {/* 9 — Revisão humana */}
          {etapa === 8 && (
            <SectionCard title="Revisão humana final">
              {!filing || !podeAprovar(filing) ? (
                <Alert variant="warning" title="Revisão indisponível">
                  Valide o ajuizamento sem erros bloqueantes antes de revisar.
                </Alert>
              ) : (
                <div className="space-y-3 text-sm">
                  <dl className="grid gap-2 sm:grid-cols-2">
                    <Item
                      rotulo="Tribunal / sistema"
                      valor={`${filing.tribunal_code} · ${filing.system}`}
                    />
                    <Item
                      rotulo="Jurisdição"
                      valor={filing.jurisdicao || "—"}
                    />
                    <Item
                      rotulo="Competência"
                      valor={filing.competencia || "—"}
                    />
                    <Item
                      rotulo="Classe"
                      valor={`${filing.classe_codigo} — ${filing.classe_nome || ""}`}
                    />
                    <Item
                      rotulo="Assuntos"
                      valor={
                        filing.assuntos.map((a) => a.codigo).join(", ") || "—"
                      }
                    />
                    <Item
                      rotulo="Valor da causa"
                      valor={filing.valor_causa || "—"}
                    />
                    <Item rotulo="Sigilo" valor={String(filing.nivel_sigilo)} />
                    <Item
                      rotulo="Gratuidade"
                      valor={filing.gratuidade ? "sim" : "não"}
                    />
                    <Item
                      rotulo="Tutela"
                      valor={filing.tutela ? "sim" : "não"}
                    />
                    <Item
                      rotulo="Anexos"
                      valor={String(filing.documentos.length)}
                    />
                  </dl>
                  <Alert variant="warning" title="Ato consciente">
                    Ao confirmar, você declara que conferiu partes, advogados,
                    petição e anexos.
                  </Alert>
                  <div>
                    <FieldLabel>{`Digite "${CONFIRMACAO_REVISAO}" para confirmar`}</FieldLabel>
                    <Input
                      value={confirmacao}
                      onChange={(e) => setConfirmacao(e.target.value)}
                    />
                  </div>
                  <div>
                    <FieldLabel>Observações da revisão (opcional)</FieldLabel>
                    <Textarea
                      value={observacoes}
                      onChange={(e) => setObservacoes(e.target.value)}
                    />
                  </div>
                  <Button
                    onClick={aprovar}
                    disabled={
                      salvando ||
                      confirmacao.trim().toUpperCase() !== CONFIRMACAO_REVISAO
                    }
                  >
                    <CheckCircle2 className="mr-1 h-4 w-4" /> Revisar e
                    protocolar
                  </Button>
                </div>
              )}
            </SectionCard>
          )}

          {/* 10 — Assinatura e protocolo */}
          {etapa === 9 && filing && (
            <div className="space-y-4">
              <SectionCard title="Assinatura">
                {filing.assinatura ? (
                  <Alert variant="success" title="Assinatura registrada">
                    {String(
                      (filing.assinatura as Record<string, string>)
                        .certificate_subject || "",
                    )}
                  </Alert>
                ) : (
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div>
                      <FieldLabel>Provedor</FieldLabel>
                      <Select
                        value={assinatura.provider}
                        onChange={(e) =>
                          setAssinatura({
                            ...assinatura,
                            provider: e.target.value,
                          })
                        }
                      >
                        <option value="registro_externo">
                          Registro de assinatura externa
                        </option>
                        <option value="pje_office">PJeOffice</option>
                        <option value="a1">Certificado A1</option>
                        <option value="a3_pkcs11">Token A3 / PKCS#11</option>
                        <option value="psc_nuvem">PSC em nuvem</option>
                      </Select>
                    </div>
                    <div>
                      <FieldLabel>Titular do certificado</FieldLabel>
                      <Input
                        value={assinatura.certificate_subject}
                        onChange={(e) =>
                          setAssinatura({
                            ...assinatura,
                            certificate_subject: e.target.value,
                          })
                        }
                      />
                    </div>
                    <div>
                      <FieldLabel>Série do certificado</FieldLabel>
                      <Input
                        value={assinatura.certificate_serial}
                        onChange={(e) =>
                          setAssinatura({
                            ...assinatura,
                            certificate_serial: e.target.value,
                          })
                        }
                      />
                    </div>
                    <div>
                      <FieldLabel>Documento assinado (do caso)</FieldLabel>
                      <Select
                        value={assinatura.signed_document_id}
                        onChange={(e) =>
                          setAssinatura({
                            ...assinatura,
                            signed_document_id: e.target.value,
                          })
                        }
                      >
                        <option value="">Selecione…</option>
                        {documentos.map((d) => (
                          <option key={d.id} value={d.id}>
                            {d.titulo || d.filename}
                          </option>
                        ))}
                      </Select>
                    </div>
                    <div className="sm:col-span-2">
                      <Button
                        onClick={assinar}
                        disabled={salvando || !podeAssinar(filing.estado)}
                      >
                        <FileSignature className="mr-1 h-4 w-4" /> Registrar
                        assinatura
                      </Button>
                    </div>
                  </div>
                )}
              </SectionCard>

              <SectionCard title="Protocolo">
                <Alert
                  variant={
                    protocoloEletronicoLiberado(matriz) ? "info" : "warning"
                  }
                  title={
                    protocoloEletronicoLiberado(matriz)
                      ? "Protocolo eletrônico liberado"
                      : "Protocolo eletrônico indisponível"
                  }
                >
                  {resumoCapacidade(matriz)}
                </Alert>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button
                    onClick={protocolar}
                    disabled={salvando || !podeProtocolar(filing)}
                  >
                    <Gavel className="mr-1 h-4 w-4" /> Protocolar pelo conector
                  </Button>
                </div>

                <div className="mt-5 border-t border-slate-200 pt-4">
                  <div className="mb-2 text-sm font-semibold text-slate-700">
                    Registrar protocolo feito no portal do tribunal
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div>
                      <FieldLabel>Número CNJ</FieldLabel>
                      <Input
                        value={manual.cnj_number}
                        onChange={(e) =>
                          setManual({ ...manual, cnj_number: e.target.value })
                        }
                        placeholder="0000000-00.0000.0.00.0000"
                      />
                    </div>
                    <div>
                      <FieldLabel>Número do protocolo</FieldLabel>
                      <Input
                        value={manual.external_protocol}
                        onChange={(e) =>
                          setManual({
                            ...manual,
                            external_protocol: e.target.value,
                          })
                        }
                      />
                    </div>
                    <div>
                      <FieldLabel>Órgão de distribuição</FieldLabel>
                      <Input
                        value={manual.distribution_unit}
                        onChange={(e) =>
                          setManual({
                            ...manual,
                            distribution_unit: e.target.value,
                          })
                        }
                      />
                    </div>
                    <div>
                      <FieldLabel>Comprovante (documento do caso)</FieldLabel>
                      <Select
                        value={manual.receipt_document_id}
                        onChange={(e) =>
                          setManual({
                            ...manual,
                            receipt_document_id: e.target.value,
                          })
                        }
                      >
                        <option value="">Selecione…</option>
                        {documentos.map((d) => (
                          <option key={d.id} value={d.id}>
                            {d.titulo || d.filename}
                          </option>
                        ))}
                      </Select>
                    </div>
                  </div>
                  <Button
                    className="mt-3"
                    variant="secondary"
                    onClick={confirmarManual}
                    disabled={salvando}
                  >
                    Registrar protocolo
                  </Button>
                </div>
              </SectionCard>
            </div>
          )}

          {/* 11 — Resultado */}
          {etapa === 10 && (
            <SectionCard title="Resultado">
              {!filing?.numero_cnj && !resultado ? (
                <EmptyState
                  title="Sem protocolo ainda"
                  message="Conclua o protocolo para ver o comprovante."
                />
              ) : (
                <div className="space-y-3 text-sm">
                  <Alert variant="success" title="Processo protocolado">
                    <dl className="grid gap-1 sm:grid-cols-2">
                      <Item
                        rotulo="Tribunal / sistema"
                        valor={`${filing?.tribunal_code} · ${filing?.system}`}
                      />
                      <Item
                        rotulo="Protocolo"
                        valor={String(
                          (resultado?.external_protocol as string) || "—",
                        )}
                      />
                      <Item
                        rotulo="Número CNJ"
                        valor={filing?.numero_cnj || "—"}
                      />
                      <Item
                        rotulo="Órgão"
                        valor={String(
                          (resultado?.distribution_unit as string) || "—",
                        )}
                      />
                      <Item
                        rotulo="Data e hora"
                        valor={
                          filing?.protocolado_em
                            ? fmtDate(filing.protocolado_em)
                            : "—"
                        }
                      />
                    </dl>
                  </Alert>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="secondary"
                      onClick={sincronizar}
                      disabled={salvando}
                    >
                      Sincronizar andamentos
                    </Button>
                    {filing?.case_id && (
                      <Link
                        className="btn-secondary"
                        to={`/casos/${filing.case_id}?tab=processos`}
                      >
                        Abrir processo no caso
                      </Link>
                    )}
                  </div>
                </div>
              )}
            </SectionCard>
          )}

          {/* Navegação */}
          <div className="mt-6 flex flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              onClick={() => setEtapa(Math.max(0, etapa - 1))}
              disabled={etapa === 0}
            >
              <ChevronLeft className="mr-1 h-4 w-4" /> Voltar
            </Button>
            {etapa < 6 && (
              <Button
                onClick={async () => {
                  if (etapa >= 1) await salvar();
                  setEtapa(etapa + 1);
                }}
                disabled={salvando || (!casoId && !filing)}
              >
                Avançar <ChevronRight className="ml-1 h-4 w-4" />
              </Button>
            )}
            {etapa === 6 && (
              <Button onClick={validar} disabled={salvando}>
                <AlertTriangle className="mr-1 h-4 w-4" /> Validar
              </Button>
            )}
            {etapa === 7 && (
              <>
                <Button
                  variant="secondary"
                  onClick={validar}
                  disabled={salvando}
                >
                  Revalidar
                </Button>
                <Button
                  onClick={() => setEtapa(8)}
                  disabled={!filing?.preflight?.ready}
                >
                  Ir para a revisão <ChevronRight className="ml-1 h-4 w-4" />
                </Button>
              </>
            )}
            {salvando && <Spinner />}
          </div>
        </>
      )}
    </div>
  );
}

function Item({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-500">
        {rotulo}
      </dt>
      <dd className="text-slate-800">{valor}</dd>
    </div>
  );
}

function mensagem(e: unknown, padrao: string): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response
    ?.data?.detail;
  if (typeof detail === "string") return detail;
  return padrao;
}
