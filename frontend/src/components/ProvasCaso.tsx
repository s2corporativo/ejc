import { useEffect, useState } from "react";
import {
  Paperclip,
  Pencil,
  Trash2,
  ArrowUp,
  ArrowDown,
  FileText,
  Scale,
  FileStack,
  Sparkles,
  AlertTriangle,
  Plus,
  ListChecks,
  CheckCircle2,
  Circle,
} from "lucide-react";
import api from "../lib/api";
import { asList } from "../lib/list";
import { toast } from "./Toast";
import {
  Modal,
  Alert,
  Spinner,
  Badge,
  FieldLabel,
  Input,
  Select,
  Textarea,
  Button,
  ConfirmModal,
} from "./UI";

// ── Contrato da API ───────────────────────────────────────────────────────────
export type ProvaTipo =
  "documental" | "pericial" | "testemunhal" | "material" | "digital" | "outro";

export interface Prova {
  id: number;
  case_id: number;
  tipo: ProvaTipo;
  titulo: string;
  descricao?: string | null;
  fato_probando?: string | null;
  document_id?: number | null;
  documento_nome?: string | null;
  tese_id?: number | null;
  tese_titulo?: string | null;
  ordem: number;
}

// Prova FALTANTE sugerida pela IA (Etapa 6 — Mapa Probatório). É SUGESTÃO/
// rascunho (HITL): quem acata cria a Prova pelo fluxo normal de cadastro.
export interface SugestaoFaltante {
  titulo: string;
  por_que_importa: string;
  como_obter: string;
  criticidade: "alta" | "media" | "baixa";
}

interface SugerirFaltantesResp {
  data: SugestaoFaltante[];
  total: number;
  aviso?: string | null;
  modelo?: string | null;
  provedor?: string | null;
}

const CRITICIDADE_UI: Record<
  SugestaoFaltante["criticidade"],
  { label: string; badge: string; card: string }
> = {
  alta: {
    label: "Criticidade alta",
    badge: "bg-danger-50 text-danger-700 ring-1 ring-danger-200",
    card: "border-danger-200",
  },
  media: {
    label: "Criticidade média",
    badge: "bg-warn-50 text-warn-700 ring-1 ring-warn-200",
    card: "border-warn-200",
  },
  baixa: {
    label: "Criticidade baixa",
    badge: "bg-slate-100 text-slate-600 ring-1 ring-slate-200",
    card: "border-slate-200",
  },
};

interface DocResumo {
  id: number;
  label: string;
}
interface TeseResumo {
  id: number;
  label: string;
}

// ── Matriz tese×prova (referência determinística — Fase C) ────────────────────
// GET /casos/{id}/provas/matriz → { data: [{ tese, provas: [...] }], total, area }
interface MatrizTese {
  tese: string;
  provas: string[];
}
interface MatrizResp {
  data: MatrizTese[];
  total: number;
  area: string;
}

// Normaliza texto p/ comparação: minúsculas, sem acento, só alfanumérico.
function normalizar(s: string): string {
  const diacriticos = /[̀-ͯ]/g;
  return s
    .toLowerCase()
    .normalize("NFD")
    .replace(diacriticos, "")
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// Heurística leve: a prova recomendada PROVAVELMENTE já está no acervo quando
// alguma prova cadastrada contém o texto recomendado, ou cobre a maioria de
// suas palavras significativas (≥4 letras). Só um indício visual — não afirma.
function provavelmentePresente(recomendada: string, corpus: string[]): boolean {
  const rec = normalizar(recomendada);
  if (!rec) return false;
  const palavras = rec.split(" ").filter((w) => w.length >= 4);
  return corpus.some((item) => {
    if (item.includes(rec)) return true;
    if (palavras.length === 0) return false;
    const casadas = palavras.filter((w) => item.includes(w)).length;
    return casadas / palavras.length >= 0.6;
  });
}

const TIPOS: { key: ProvaTipo; label: string }[] = [
  { key: "documental", label: "Documental" },
  { key: "pericial", label: "Pericial" },
  { key: "testemunhal", label: "Testemunhal" },
  { key: "material", label: "Material" },
  { key: "digital", label: "Digital" },
  { key: "outro", label: "Outro" },
];

// Cor do badge por tipo de prova (paleta do design system)
const TIPO_COR: Record<ProvaTipo, string> = {
  documental: "bg-primary-50 text-primary-700 ring-1 ring-primary-200",
  pericial: "bg-ai-50 text-ai-700 ring-1 ring-ai-200",
  testemunhal: "bg-warn-50 text-warn-700 ring-1 ring-warn-200",
  material: "bg-success-50 text-success-700 ring-1 ring-success-200",
  digital: "bg-info-50 text-info-700 ring-1 ring-info-200",
  outro: "bg-slate-100 text-slate-600 ring-1 ring-slate-200",
};

const TIPO_LABEL: Record<ProvaTipo, string> = Object.fromEntries(
  TIPOS.map((t) => [t.key, t.label]),
) as Record<ProvaTipo, string>;

function apiDetail(e: unknown, fallback: string): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response
    ?.data?.detail;
  return typeof detail === "string" ? detail : fallback;
}

interface FormState {
  tipo: ProvaTipo;
  titulo: string;
  descricao: string;
  fato_probando: string;
  document_id: string;
  tese_id: string;
}

const FORM_VAZIO: FormState = {
  tipo: "documental",
  titulo: "",
  descricao: "",
  fato_probando: "",
  document_id: "",
  tese_id: "",
};

export default function ProvasCaso({ caseId }: { caseId: string | number }) {
  const [provas, setProvas] = useState<Prova[]>([]);
  const [docs, setDocs] = useState<DocResumo[]>([]);
  const [teses, setTeses] = useState<TeseResumo[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState("");

  const [formOpen, setFormOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState<FormState>(FORM_VAZIO);
  const [formErro, setFormErro] = useState("");
  const [salvando, setSalvando] = useState(false);

  const [excluirId, setExcluirId] = useState<number | null>(null);
  const [excluindo, setExcluindo] = useState(false);
  const [reordenando, setReordenando] = useState(false);
  const [gerandoPdf, setGerandoPdf] = useState(false);

  // MATRIZ tese×prova (referência determinística — Fase C, sem IA)
  const [matriz, setMatriz] = useState<MatrizTese[]>([]);
  const [matrizArea, setMatrizArea] = useState("");
  const [matrizLoading, setMatrizLoading] = useState(true);

  // PROVAS FALTANTES (sugestão da IA — Etapa 6 do Mapa Probatório)
  const [sugestoes, setSugestoes] = useState<SugestaoFaltante[]>([]);
  const [sugerindo, setSugerindo] = useState(false);
  const [avisoIa, setAvisoIa] = useState("");
  const [sugeriu, setSugeriu] = useState(false);
  // índice da sugestão sendo acatada — removida da lista após o cadastro
  const [sugestaoIdx, setSugestaoIdx] = useState<number | null>(null);

  const carregar = () => {
    setErro("");
    return api
      .get(`/casos/${caseId}/provas`)
      .then((r) => {
        const lista: Prova[] = asList<Prova>(r.data);
        lista.sort((a, b) => (a.ordem ?? 0) - (b.ordem ?? 0));
        setProvas(lista);
      })
      .catch((e) =>
        setErro(apiDetail(e, "Falha ao carregar as provas do caso.")),
      )
      .finally(() => setLoading(false));
  };

  // Documentos do caso para vínculo opcional (endpoint existente /documents/).
  // O GED limita páginas a 100; percorremos todas as páginas em vez de pedir
  // 500 de uma vez (que passa a responder 422 no contrato endurecido).
  const carregarDocs = async () => {
    try {
      const pageSize = 100;
      let page = 1;
      let total = Number.POSITIVE_INFINITY;
      const all: any[] = [];
      while (all.length < total) {
        const response = await api.get("/documents/", {
          params: { case_id: caseId, page, page_size: pageSize },
        });
        const lote = asList(response.data);
        all.push(...lote);
        total = Number(response.data?.total ?? all.length);
        if (lote.length < pageSize) break;
        page += 1;
        if (page > 100) break;
      }
      setDocs(
        all.map((d: any) => ({
          id: d.id,
          label:
            d.titulo || d.nome_arquivo || d.filename || `Documento ${d.id}`,
        })),
      );
    } catch {
      setDocs([]);
    }
  };

  // Matriz tese×prova (referência estática). Erro é silencioso: não pode
  // quebrar a tela — degrada para lista vazia (estado vazio discreto).
  const carregarMatriz = () => {
    setMatrizLoading(true);
    return api
      .get<MatrizResp>(`/casos/${caseId}/provas/matriz`)
      .then((r) => {
        setMatriz(asList<MatrizTese>(r.data));
        setMatrizArea(r.data?.area || "");
      })
      .catch(() => {
        setMatriz([]);
        setMatrizArea("");
      })
      .finally(() => setMatrizLoading(false));
  };

  // Teses/pedidos vinculados ao caso para vínculo opcional
  const carregarTeses = () =>
    api
      .get(`/teses/casos/${caseId}`)
      .then((r) => {
        const all = asList(r.data);
        setTeses(
          all.map((t: any) => ({
            id: t.id,
            label: t.titulo || `Tese ${t.id}`,
          })),
        );
      })
      .catch(() => setTeses([]));

  useEffect(() => {
    setLoading(true);
    setSugestoes([]);
    setAvisoIa("");
    setSugeriu(false);
    setSugestaoIdx(null);
    carregar();
    void carregarDocs();
    carregarTeses();
    carregarMatriz();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  // IA sugere provas FALTANTES (endpoint caro: rate-limited, botão disabled)
  const sugerirComIA = async () => {
    if (sugerindo) return;
    setSugerindo(true);
    setAvisoIa("");
    try {
      const r = await api.post<SugerirFaltantesResp>(
        `/casos/${caseId}/provas/sugerir-faltantes`,
      );
      setSugestoes(asList<SugestaoFaltante>(r.data));
      setAvisoIa(r.data?.aviso || "");
      setSugeriu(true);
    } catch (e) {
      setSugestoes([]);
      setAvisoIa(
        apiDetail(e, "Falha ao gerar sugestões de provas faltantes com a IA."),
      );
      setSugeriu(true);
    } finally {
      setSugerindo(false);
    }
  };

  const abrirNova = () => {
    setEditId(null);
    setSugestaoIdx(null);
    setForm(FORM_VAZIO);
    setFormErro("");
    setFormOpen(true);
  };

  // Acata uma sugestão da IA: abre o formulário NORMAL de cadastro pré-preenchido
  // (HITL — a prova só entra no mapa depois que o advogado revisar e salvar).
  const abrirDeSugestao = (s: SugestaoFaltante, idx: number) => {
    setEditId(null);
    setSugestaoIdx(idx);
    setForm({
      ...FORM_VAZIO,
      titulo: s.titulo,
      fato_probando: s.por_que_importa,
      descricao: s.como_obter ? `Como obter: ${s.como_obter}` : "",
    });
    setFormErro("");
    setFormOpen(true);
  };

  const abrirEdicao = (p: Prova) => {
    setEditId(p.id);
    setSugestaoIdx(null);
    setForm({
      tipo: p.tipo,
      titulo: p.titulo,
      descricao: p.descricao ?? "",
      fato_probando: p.fato_probando ?? "",
      document_id: p.document_id != null ? String(p.document_id) : "",
      tese_id: p.tese_id != null ? String(p.tese_id) : "",
    });
    setFormErro("");
    setFormOpen(true);
  };

  const salvar = async () => {
    if (!form.titulo.trim()) {
      setFormErro("Informe o título da prova.");
      return;
    }
    setSalvando(true);
    setFormErro("");
    const payload: Record<string, unknown> = {
      tipo: form.tipo,
      titulo: form.titulo.trim(),
      descricao: form.descricao.trim() || null,
      fato_probando: form.fato_probando.trim() || null,
      document_id: form.document_id ? Number(form.document_id) : null,
      tese_id: form.tese_id ? Number(form.tese_id) : null,
    };
    try {
      if (editId != null) {
        await api.patch(`/casos/${caseId}/provas/${editId}`, payload);
        toast.success("Prova atualizada.");
      } else {
        payload.ordem = provas.length
          ? Math.max(...provas.map((p) => p.ordem ?? 0)) + 1
          : 1;
        await api.post(`/casos/${caseId}/provas`, payload);
        toast.success("Prova cadastrada.");
        // Sugestão da IA acatada → sai da lista de faltantes.
        if (sugestaoIdx != null) {
          setSugestoes((s) => s.filter((_, i) => i !== sugestaoIdx));
          setSugestaoIdx(null);
        }
      }
      setFormOpen(false);
      await carregar();
    } catch (e) {
      setFormErro(apiDetail(e, "Falha ao salvar a prova."));
    } finally {
      setSalvando(false);
    }
  };

  const excluir = async () => {
    if (excluirId == null) return;
    setExcluindo(true);
    try {
      await api.delete(`/casos/${caseId}/provas/${excluirId}`);
      toast.success("Prova removida.");
      setExcluirId(null);
      await carregar();
    } catch (e) {
      toast.error(apiDetail(e, "Falha ao remover a prova."));
    } finally {
      setExcluindo(false);
    }
  };

  // Move ↑/↓ trocando a `ordem` com o vizinho (PATCH em ambos)
  const mover = async (index: number, dir: -1 | 1) => {
    const vizinho = index + dir;
    if (vizinho < 0 || vizinho >= provas.length || reordenando) return;
    const atual = provas[index];
    const outro = provas[vizinho];
    setReordenando(true);
    try {
      await Promise.all([
        api.patch(`/casos/${caseId}/provas/${atual.id}`, {
          ordem: outro.ordem,
        }),
        api.patch(`/casos/${caseId}/provas/${outro.id}`, {
          ordem: atual.ordem,
        }),
      ]);
      await carregar();
    } catch (e) {
      toast.error(apiDetail(e, "Falha ao reordenar as provas."));
    } finally {
      setReordenando(false);
    }
  };

  // Documento Único de Anexos (Visual Law) — POST → download_url → blob
  const gerarDocumentoUnico = async () => {
    setGerandoPdf(true);
    try {
      const r = await api.post(`/casos/${caseId}/provas/documento-unico`);
      const downloadUrl: string | undefined = r.data?.download_url;
      if (!downloadUrl) throw new Error("download_url ausente na resposta");
      const blob = await api.get(downloadUrl.replace(/^\/api/, ""), {
        responseType: "blob",
      });
      const url = URL.createObjectURL(blob.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "documento-unico-anexos.pdf";
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Documento único de anexos (Visual Law) gerado.");
    } catch (e) {
      toast.error(apiDetail(e, "Falha ao gerar o documento único de anexos."));
    } finally {
      setGerandoPdf(false);
    }
  };

  // Corpus normalizado do acervo já cadastrado (título + descrição + fato),
  // usado só para o indício visual "provável no acervo" na matriz.
  const corpusProvas = provas.map((p) =>
    normalizar([p.titulo, p.descricao ?? "", p.fato_probando ?? ""].join(" ")),
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Paperclip size={18} className="text-gold-600" />
          <div>
            <h2 className="font-semibold text-navy">
              Acervo probatório ({provas.length})
            </h2>
            <p className="text-xs text-slate-500">
              Organize as provas do caso, o que cada uma comprova e seus
              vínculos com documentos e teses.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={gerarDocumentoUnico}
            disabled={gerandoPdf || provas.length === 0}
            className="btn-gold flex items-center gap-1.5 text-sm disabled:opacity-50"
          >
            <FileStack size={15} />
            {gerandoPdf
              ? "Gerando…"
              : "Gerar Documento Único de Anexos (Visual Law)"}
          </button>
          <Button size="sm" onClick={abrirNova} icon={<Paperclip size={15} />}>
            Nova prova
          </Button>
        </div>
      </div>

      {erro && <Alert variant="danger">{erro}</Alert>}

      {loading ? (
        <Spinner />
      ) : provas.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-200 bg-white px-6 py-12 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-gold-50 text-gold-600">
            <Paperclip className="h-6 w-6" />
          </div>
          <h3 className="text-sm font-semibold text-slate-900">
            Nenhuma prova cadastrada
          </h3>
          <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">
            Organize aqui o acervo probatório do caso — registre cada prova, o
            que ela comprova e seus vínculos.
          </p>
          <div className="mt-4 flex justify-center">
            <Button
              size="sm"
              onClick={abrirNova}
              icon={<Paperclip size={15} />}
            >
              Cadastrar primeira prova
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {provas.map((p, i) => (
            <div key={p.id} className="card p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 flex-1 items-start gap-3">
                  <div className="flex flex-col items-center gap-1 pt-0.5">
                    <button
                      onClick={() => mover(i, -1)}
                      disabled={i === 0 || reordenando}
                      title="Mover para cima"
                      className="text-slate-400 hover:text-navy disabled:opacity-30"
                    >
                      <ArrowUp size={16} />
                    </button>
                    <span className="text-xs font-semibold text-slate-400">
                      {i + 1}
                    </span>
                    <button
                      onClick={() => mover(i, 1)}
                      disabled={i === provas.length - 1 || reordenando}
                      title="Mover para baixo"
                      className="text-slate-400 hover:text-navy disabled:opacity-30"
                    >
                      <ArrowDown size={16} />
                    </button>
                  </div>

                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <span
                        className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${TIPO_COR[p.tipo]}`}
                      >
                        {TIPO_LABEL[p.tipo] ?? p.tipo}
                      </span>
                      <span className="font-medium text-slate-900">
                        {p.titulo}
                      </span>
                    </div>
                    {p.descricao && (
                      <p className="mb-1 text-sm text-slate-600">
                        {p.descricao}
                      </p>
                    )}
                    {p.fato_probando && (
                      <p className="mb-2 text-sm text-slate-700">
                        <span className="font-medium text-gold-700">
                          Fato probando:{" "}
                        </span>
                        {p.fato_probando}
                      </p>
                    )}
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
                      {p.document_id != null && (
                        <span className="inline-flex items-center gap-1">
                          <FileText size={13} />
                          {p.documento_nome || `Documento #${p.document_id}`}
                        </span>
                      )}
                      {p.tese_id != null && (
                        <span className="inline-flex items-center gap-1">
                          <Scale size={13} />
                          {p.tese_titulo || `Tese #${p.tese_id}`}
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                <div className="flex shrink-0 items-center gap-1">
                  <button
                    onClick={() => abrirEdicao(p)}
                    title="Editar"
                    className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-navy"
                  >
                    <Pencil size={16} />
                  </button>
                  <button
                    onClick={() => setExcluirId(p.id)}
                    title="Excluir"
                    className="rounded-lg p-1.5 text-slate-400 hover:bg-danger-50 hover:text-danger-600"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── PROVA MÍNIMA RECOMENDADA (matriz tese×prova — referência estática) ── */}
      <section
        aria-labelledby="matriz-prova-titulo"
        className="rounded-2xl border border-gold-200 bg-gold-50/40 p-4"
      >
        <div className="flex items-center gap-2">
          <ListChecks size={18} className="text-gold-600" />
          <div>
            <h3
              id="matriz-prova-titulo"
              className="text-sm font-semibold text-navy"
            >
              Prova mínima recomendada (matriz tese×prova)
            </h3>
            <p className="text-xs text-slate-500">
              Referência determinística das provas mínimas típicas por
              tese/pedido
              {matrizArea ? ` · área: ${matrizArea}` : ""}. O indício “provável
              no acervo” é apenas orientativo.
            </p>
          </div>
        </div>

        {matrizLoading ? (
          <Spinner />
        ) : matriz.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">
            Sem recomendações para esta área/tese.
          </p>
        ) : (
          <div className="mt-3 space-y-3">
            {matriz.map((linha, li) => (
              <div
                key={`${linha.tese}-${li}`}
                className="rounded-xl border border-gold-100 bg-white p-3 shadow-sm"
              >
                <div className="mb-2 flex items-center gap-1.5">
                  <Scale size={14} className="text-gold-700" />
                  <span className="text-sm font-medium text-slate-900">
                    {linha.tese}
                  </span>
                </div>
                <ul className="space-y-1.5">
                  {linha.provas.map((rec, pi) => {
                    const provavel = provavelmentePresente(rec, corpusProvas);
                    return (
                      <li
                        key={`${rec}-${pi}`}
                        className="flex flex-wrap items-center gap-2 text-sm text-slate-700"
                      >
                        {provavel ? (
                          <CheckCircle2
                            size={15}
                            className="shrink-0 text-success-600"
                            aria-hidden
                          />
                        ) : (
                          <Circle
                            size={15}
                            className="shrink-0 text-slate-300"
                            aria-hidden
                          />
                        )}
                        <span className="min-w-0 flex-1">{rec}</span>
                        {provavel ? (
                          <Badge tone="green">Provável no acervo</Badge>
                        ) : (
                          <Badge tone="slate">Recomendada</Badge>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ── PROVAS FALTANTES (sugestão da IA — Etapa 6 do Mapa Probatório) ── */}
      <div className="rounded-2xl border border-ai-200 bg-ai-50/40 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Sparkles size={18} className="text-ai-600" />
            <div>
              <h3 className="text-sm font-semibold text-navy">
                Provas faltantes (sugestão da IA)
              </h3>
              <p className="text-xs text-slate-500">
                A IA aponta provas típicas para este tipo de ação que ainda não
                estão no mapa — com justificativa probatória e como obter.
              </p>
            </div>
          </div>
          <Button
            size="sm"
            onClick={sugerirComIA}
            disabled={sugerindo || loading}
            icon={<Sparkles size={15} />}
          >
            {sugerindo ? "Analisando o caso…" : "Sugerir com IA"}
          </Button>
        </div>

        <p className="mt-2 text-[11px] text-slate-500">
          Sugestões geradas por IA são <strong>rascunho de apoio</strong> — não
          criam nada automaticamente. A avaliação e o cadastro de cada prova são
          do advogado (revisão humana obrigatória).
        </p>

        {avisoIa && (
          <div className="mt-3">
            <Alert variant="warning">{avisoIa}</Alert>
          </div>
        )}

        {sugerindo ? (
          <div className="mt-4">
            <Spinner />
          </div>
        ) : sugestoes.length > 0 ? (
          <div className="mt-3 space-y-2">
            {sugestoes.map((s, idx) => {
              const ui = CRITICIDADE_UI[s.criticidade] ?? CRITICIDADE_UI.media;
              return (
                <div
                  key={`${s.titulo}-${idx}`}
                  className={`rounded-xl border bg-white p-3 shadow-sm ${ui.card}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="mb-1 flex flex-wrap items-center gap-2">
                        <AlertTriangle
                          size={15}
                          className={
                            s.criticidade === "alta"
                              ? "text-danger-600"
                              : s.criticidade === "media"
                                ? "text-warn-600"
                                : "text-slate-400"
                          }
                        />
                        <span className="font-medium text-slate-900">
                          {s.titulo}
                        </span>
                        <span
                          className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${ui.badge}`}
                        >
                          {ui.label}
                        </span>
                      </div>
                      {s.por_que_importa && (
                        <p className="text-sm text-slate-700">
                          <span className="font-medium text-gold-700">
                            Por que importa:{" "}
                          </span>
                          {s.por_que_importa}
                        </p>
                      )}
                      {s.como_obter && (
                        <p className="mt-0.5 text-xs text-slate-500">
                          <span className="font-medium">Como obter: </span>
                          {s.como_obter}
                        </p>
                      )}
                    </div>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => abrirDeSugestao(s, idx)}
                      icon={<Plus size={14} />}
                    >
                      Adicionar ao mapa
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          sugeriu &&
          !avisoIa && (
            <p className="mt-3 text-sm text-slate-500">
              Nenhuma prova faltante sugerida — o mapa probatório parece cobrir
              o essencial para este tipo de ação.
            </p>
          )
        )}
      </div>

      {/* ── Formulário criar/editar ────────────────────────────────────────── */}
      <Modal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        title={editId != null ? "Editar prova" : "Nova prova"}
      >
        <div className="space-y-3">
          {formErro && <Alert variant="danger">{formErro}</Alert>}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <FieldLabel required>Tipo de prova</FieldLabel>
              <Select
                value={form.tipo}
                onChange={(e) =>
                  setForm((f) => ({ ...f, tipo: e.target.value as ProvaTipo }))
                }
              >
                {TIPOS.map((t) => (
                  <option key={t.key} value={t.key}>
                    {t.label}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <FieldLabel required>Título</FieldLabel>
              <Input
                value={form.titulo}
                onChange={(e) =>
                  setForm((f) => ({ ...f, titulo: e.target.value }))
                }
                placeholder="Ex.: Contrato assinado"
              />
            </div>
          </div>
          <div>
            <FieldLabel>Descrição</FieldLabel>
            <Textarea
              rows={2}
              value={form.descricao}
              onChange={(e) =>
                setForm((f) => ({ ...f, descricao: e.target.value }))
              }
              placeholder="Detalhes da prova (opcional)"
            />
          </div>
          <div>
            <FieldLabel>Fato probando</FieldLabel>
            <Textarea
              rows={2}
              value={form.fato_probando}
              onChange={(e) =>
                setForm((f) => ({ ...f, fato_probando: e.target.value }))
              }
              placeholder="O que esta prova prova (ex.: comprova a relação contratual)"
            />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <FieldLabel>Documento vinculado</FieldLabel>
              <Select
                value={form.document_id}
                onChange={(e) =>
                  setForm((f) => ({ ...f, document_id: e.target.value }))
                }
              >
                <option value="">— sem vínculo —</option>
                {docs.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.label}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <FieldLabel>Tese / pedido vinculado</FieldLabel>
              <Select
                value={form.tese_id}
                onChange={(e) =>
                  setForm((f) => ({ ...f, tese_id: e.target.value }))
                }
              >
                <option value="">— sem vínculo —</option>
                {teses.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.label}
                  </option>
                ))}
              </Select>
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setFormOpen(false)}
            >
              Cancelar
            </Button>
            <Button size="sm" onClick={salvar} disabled={salvando}>
              {salvando ? "Salvando…" : editId != null ? "Salvar" : "Cadastrar"}
            </Button>
          </div>
        </div>
      </Modal>

      <ConfirmModal
        open={excluirId != null}
        onClose={() => setExcluirId(null)}
        onConfirm={excluir}
        variant="danger"
        title="Excluir prova"
        message="Esta prova será removida do acervo probatório do caso."
        confirmLabel="Excluir"
        loading={excluindo}
      />
    </div>
  );
}