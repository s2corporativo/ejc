/**
 * Sala Jurídica Conversacional (V1) — porta de entrada da IA no EJC.
 *
 * Layout em 3 colunas (validado em protótipo): sessões à esquerda, área de
 * trabalho livre + chat ao centro, estado jurídico consolidado à direita.
 * Toda IA passa pelo backend (/api/sala-juridica/*), que roda o núcleo único
 * (sanitização LGPD → RAG → AILog → HITL) — esta tela nunca chama modelo.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Archive,
  FolderInput,
  Loader2,
  MessageSquareText,
  Paperclip,
  Plus,
  Scale,
  Send,
  Star,
  UploadCloud,
} from "lucide-react";
import api from "../lib/api";
import Markdown from "../components/Markdown";
import { useAuth } from "../stores/auth";
import { toast } from "../components/Toast";
import {
  AIFactualityLegend,
  Badge,
  Button,
  EmptyState,
  Input,
  PageHeader,
  Select,
  Textarea,
  cn,
} from "../components/UI";

type Mensagem = {
  id: string;
  autor: "user" | "ia";
  modo: string;
  conteudo: string;
  modelo?: string | null;
  agente?: string | null;
  fontes: Array<{ titulo?: string; categoria?: string; fonte?: string }>;
  alertas: string[];
  custo_estimado?: number | null;
  estado_versao?: number | null;
  created_at?: string | null;
};

type Anexo = {
  id: string;
  nome_original: string;
  size_bytes: number;
  ocr_utilizado: boolean;
  tipo_documento?: string | null;
};

type Estado = {
  versao: number;
  resumo?: string | null;
  estado: Record<string, Array<Record<string, unknown>>>;
  origem?: string | null;
};

type Sessao = {
  id: string;
  titulo: string;
  status: string;
  favorita: boolean;
  cliente_potencial?: string | null;
  area_sugerida?: string | null;
  workspace_versao: number;
  convertido_case_id?: string | null;
  frozen: boolean;
  custo_ia_total: number;
  updated_at?: string | null;
  workspace_texto?: string | null;
  mensagens?: Mensagem[];
  anexos?: Anexo[];
  estado?: Estado | null;
};

const STATUS_LABEL: Record<string, string> = {
  em_analise: "Em análise",
  aguardando_documentos: "Aguardando docs",
  pronta_para_caso: "Pronta p/ caso",
  convertida_em_caso: "Convertida",
  arquivada: "Arquivada",
};

const MODOS: Array<{ valor: string; rotulo: string }> = [
  { valor: "conversa_livre", rotulo: "Conversa livre" },
  { valor: "organizar_fatos", rotulo: "Organizar fatos" },
  { valor: "analisar_provas", rotulo: "Analisar provas" },
  { valor: "detectar_contradicoes", rotulo: "Detectar contradições" },
  { valor: "estrategia_da_parte", rotulo: "Estratégia da parte" },
  { valor: "simular_defesa", rotulo: "Simular defesa" },
  { valor: "julgar_caso", rotulo: "Julgar o caso" },
  { valor: "pesquisar_direito", rotulo: "Pesquisar direito" },
  { valor: "elaborar_documento", rotulo: "Elaborar documento" },
  { valor: "revisar_documento", rotulo: "Revisar documento" },
];

const ABAS_ESTADO = [
  "fatos",
  "provas",
  "contradicoes",
  "teses",
  "riscos",
  "pendencias",
  "cronologia",
  "fontes",
] as const;

const CLASSIFICACAO_COR: Record<string, string> = {
  comprovado: "bg-emerald-100 text-emerald-800",
  alegado: "bg-amber-100 text-amber-800",
  inferido: "bg-sky-100 text-sky-800",
  controvertido: "bg-violet-100 text-violet-800",
  ausente: "bg-red-100 text-red-800",
  superado: "bg-gray-200 text-gray-500 line-through",
};

export default function SalaJuridica() {
  const { user } = useAuth();
  const [sessoes, setSessoes] = useState<Sessao[]>([]);
  const [ativa, setAtiva] = useState<Sessao | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [enviando, setEnviando] = useState(false);
  const [texto, setTexto] = useState("");
  const [modo, setModo] = useState("conversa_livre");
  const [workspace, setWorkspace] = useState("");
  const [abaEstado, setAbaEstado] = useState<(typeof ABAS_ESTADO)[number]>("fatos");
  const [busca, setBusca] = useState("");
  const chatRef = useRef<HTMLDivElement>(null);
  const autosaveRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const carregarLista = useCallback(async () => {
    const { data } = await api.get<Sessao[]>("/sala-juridica");
    setSessoes(data);
    return data;
  }, []);

  const abrirSessao = useCallback(async (id: string) => {
    const { data } = await api.get<Sessao>(`/sala-juridica/${id}`);
    setAtiva(data);
    setWorkspace(data.workspace_texto ?? "");
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const lista = await carregarLista();
        if (lista.length > 0) await abrirSessao(lista[0].id);
      } catch {
        toast.error("Falha ao carregar a Sala Jurídica");
      } finally {
        setCarregando(false);
      }
    })();
  }, [carregarLista, abrirSessao, toast]);

  useEffect(() => {
    chatRef.current?.scrollTo({ top: chatRef.current.scrollHeight });
  }, [ativa?.mensagens?.length]);

  const novaSessao = async () => {
    const { data } = await api.post<Sessao>("/sala-juridica", {
      titulo: `Nova análise — ${new Date().toLocaleDateString("pt-BR")}`,
    });
    await carregarLista();
    await abrirSessao(data.id);
  };

  // Autosave da área livre (debounce 1,2s) — nunca grava sessão congelada.
  const aoEditarWorkspace = (valor: string) => {
    setWorkspace(valor);
    if (!ativa || ativa.frozen) return;
    if (autosaveRef.current) clearTimeout(autosaveRef.current);
    autosaveRef.current = setTimeout(async () => {
      try {
        await api.patch(`/sala-juridica/${ativa.id}`, { workspace_texto: valor });
      } catch {
        toast.error("Falha no salvamento automático");
      }
    }, 1200);
  };

  const enviar = async () => {
    if (!ativa || !texto.trim() || enviando) return;
    const conteudo = texto.trim();
    setTexto("");
    setEnviando(true);
    setAtiva((s) =>
      s
        ? {
            ...s,
            mensagens: [
              ...(s.mensagens ?? []),
              {
                id: `tmp-${Date.now()}`,
                autor: "user",
                modo,
                conteudo,
                fontes: [],
                alertas: [],
              },
            ],
          }
        : s,
    );
    try {
      await api.post(`/sala-juridica/${ativa.id}/mensagens`, { conteudo, modo });
      await abrirSessao(ativa.id);
      await carregarLista();
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Falha ao enviar a mensagem";
      toast.error(String(detail));
      setTexto(conteudo);
    } finally {
      setEnviando(false);
    }
  };

  const anexar = async (files: FileList | null) => {
    if (!ativa || !files?.length) return;
    const form = new FormData();
    Array.from(files).forEach((f) => form.append("files", f));
    try {
      const { data } = await api.post(`/sala-juridica/${ativa.id}/anexos`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const anexados = (data?.anexados ?? []).length;
      toast.success(`${anexados} documento(s) anexado(s) e extraído(s)`);
      await abrirSessao(ativa.id);
    } catch {
      toast.error("Falha no upload dos documentos");
    }
  };

  const alternarFavorita = async (s: Sessao) => {
    await api.patch(`/sala-juridica/${s.id}`, { favorita: !s.favorita });
    await carregarLista();
  };

  const arquivar = async () => {
    if (!ativa) return;
    await api.post(`/sala-juridica/${ativa.id}/saida`, { acao: "arquivar" });
    toast.success("Análise arquivada");
    await carregarLista();
  };

  const sessoesFiltradas = useMemo(() => {
    const q = busca.trim().toLowerCase();
    if (!q) return sessoes;
    return sessoes.filter(
      (s) =>
        s.titulo.toLowerCase().includes(q) ||
        (s.cliente_potencial ?? "").toLowerCase().includes(q),
    );
  }, [sessoes, busca]);

  const grupos = useMemo(() => {
    const ordem = [
      "em_analise",
      "aguardando_documentos",
      "pronta_para_caso",
      "convertida_em_caso",
      "arquivada",
    ];
    return ordem
      .map((st) => ({
        status: st,
        itens: sessoesFiltradas.filter((s) => s.status === st),
      }))
      .filter((g) => g.itens.length > 0);
  }, [sessoesFiltradas]);

  const estadoAtual = ativa?.estado?.estado ?? {};

  if (carregando) {
    return (
      <div className="flex h-64 items-center justify-center text-gray-500">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Carregando a Sala Jurídica…
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Sala Jurídica"
        subtitle="Converse livremente — o EJC estrutura fatos, provas e estratégia por trás da tela. Conteúdo de IA é rascunho sujeito a revisão humana (OAB)."
        actions={
          <div className="flex gap-2">
            <Button variant="secondary" onClick={arquivar} disabled={!ativa || ativa.frozen}>
              <Archive className="h-4 w-4" /> Arquivar
            </Button>
            <Button
              variant="secondary"
              disabled={!ativa || ativa.frozen}
              onClick={() =>
                toast.info(
                  "Conversão em caso: confira cliente, conflito, área e responsável na próxima etapa (POST /converter)",
                )
              }
            >
              <FolderInput className="h-4 w-4" /> Transformar em caso
            </Button>
            <Button onClick={novaSessao}>
              <Plus className="h-4 w-4" /> Nova análise
            </Button>
          </div>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[280px_1fr_320px]">
        {/* ── Coluna esquerda: sessões ─────────────────────────────────── */}
        <aside className="space-y-3">
          <Input
            placeholder="Pesquisar análises…"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
          {grupos.length === 0 && (
            <EmptyState
              icon={MessageSquareText}
              title="Nenhuma análise"
              message="Crie uma nova análise para começar."
            />
          )}
          {grupos.map((g) => (
            <div key={g.status}>
              <p className="mb-1 text-[11px] font-bold uppercase tracking-wide text-gray-500">
                {STATUS_LABEL[g.status]} · {g.itens.length}
              </p>
              {g.itens.map((s) => (
                <button
                  key={s.id}
                  onClick={() => abrirSessao(s.id)}
                  className={cn(
                    "mb-1 w-full rounded-lg border p-2 text-left text-sm transition",
                    ativa?.id === s.id
                      ? "border-primary-300 bg-primary-50"
                      : "border-gray-200 bg-white hover:border-gray-300",
                  )}
                >
                  <span className="flex items-start justify-between gap-1">
                    <span className="font-medium leading-tight">{s.titulo}</span>
                    <Star
                      className={cn(
                        "h-4 w-4 shrink-0",
                        s.favorita ? "fill-amber-400 text-amber-400" : "text-gray-300",
                      )}
                      onClick={(e) => {
                        e.stopPropagation();
                        void alternarFavorita(s);
                      }}
                    />
                  </span>
                  <span className="mt-1 flex flex-wrap gap-1">
                    <Badge tone="blue">{s.area_sugerida ?? "sem área"}</Badge>
                    {s.custo_ia_total > 0 && (
                      <Badge tone="slate">R$ {s.custo_ia_total.toFixed(2)}</Badge>
                    )}
                    {s.frozen && <Badge tone="amber">congelada</Badge>}
                  </span>
                </button>
              ))}
            </div>
          ))}
        </aside>

        {/* ── Centro: área livre + chat ────────────────────────────────── */}
        <section className="flex min-h-[70vh] flex-col gap-3">
          {ativa ? (
            <>
              <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
                <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2 text-xs text-gray-500">
                  <span className="font-semibold text-gray-700">
                    Área de trabalho livre
                  </span>
                  <span>
                    v{ativa.workspace_versao} · salvamento automático
                    {ativa.frozen && " · congelada (auditoria)"}
                  </span>
                </div>
                <Textarea
                  className="min-h-[160px] w-full resize-y border-0 focus:ring-0"
                  placeholder="Cole fatos, narrativas do cliente, rascunhos, trechos de peças…"
                  value={workspace}
                  disabled={ativa.frozen}
                  onChange={(e) => aoEditarWorkspace(e.target.value)}
                />
              </div>

              <div
                ref={chatRef}
                className="flex-1 space-y-3 overflow-y-auto rounded-xl border border-gray-200 bg-gray-50 p-3"
              >
                {(ativa.mensagens ?? []).length === 0 && (
                  <EmptyState
                    icon={MessageSquareText}
                    title="Comece a conversa"
                    message='Ex.: "Analise juridicamente este caso. Represento a ré."'
                  />
                )}
                {(ativa.mensagens ?? []).map((m) => (
                  <div
                    key={m.id}
                    className={cn(
                      "rounded-lg border p-3 text-sm",
                      m.autor === "user"
                        ? "border-blue-100 bg-blue-50"
                        : "border-gray-200 bg-white shadow-sm",
                    )}
                  >
                    <p className="mb-1 flex flex-wrap items-center gap-2 text-[11px] font-semibold text-gray-500">
                      {m.autor === "user" ? user?.full_name ?? "Você" : "Sala Jurídica · IA"}
                      <Badge tone="blue">{m.modo.replace(/_/g, " ")}</Badge>
                      {m.autor === "ia" && m.modelo && <Badge tone="slate">{m.modelo}</Badge>}
                      {m.estado_versao != null && (
                        <Badge tone="green">estado v{m.estado_versao}</Badge>
                      )}
                    </p>
                    {m.autor === "ia" ? (
                      <Markdown source={m.conteudo} />
                    ) : (
                      <p className="whitespace-pre-wrap">{m.conteudo}</p>
                    )}
                    {m.autor === "ia" && m.fontes.length > 0 && (
                      <p className="mt-2 flex flex-wrap gap-1">
                        {m.fontes.map((f, i) => (
                          <Badge key={i} tone="amber">
                            {f.titulo ?? f.fonte ?? "fonte"}
                          </Badge>
                        ))}
                      </p>
                    )}
                    {m.autor === "ia" && m.alertas.length > 0 && (
                      <ul className="mt-2 list-disc pl-5 text-xs text-amber-700">
                        {m.alertas.map((a, i) => (
                          <li key={i}>{a}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
                {enviando && (
                  <p className="flex items-center gap-2 text-sm text-gray-500">
                    <Loader2 className="h-4 w-4 animate-spin" /> Analisando (sanitização →
                    RAG → validação → AILog)…
                  </p>
                )}
              </div>

              <div className="rounded-xl border border-gray-200 bg-white p-2 shadow-sm">
                <Textarea
                  className="min-h-[56px] w-full resize-none border-0 focus:ring-0"
                  placeholder="Converse livremente ou dê um comando jurídico…"
                  value={texto}
                  disabled={ativa.frozen || enviando}
                  onChange={(e) => setTexto(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void enviar();
                    }
                  }}
                />
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <input
                    ref={fileRef}
                    type="file"
                    multiple
                    hidden
                    onChange={(e) => void anexar(e.target.files)}
                  />
                  <Button
                    variant="secondary"
                    disabled={ativa.frozen}
                    onClick={() => fileRef.current?.click()}
                  >
                    <Paperclip className="h-4 w-4" /> Anexar
                  </Button>
                  <Select
                    value={modo}
                    onChange={(e) => setModo(e.target.value)}
                    className="max-w-[220px]"
                  >
                    {MODOS.map((m) => (
                      <option key={m.valor} value={m.valor}>
                        {m.rotulo}
                      </option>
                    ))}
                  </Select>
                  <span className="ml-auto">
                    <Button onClick={() => void enviar()} disabled={ativa.frozen || enviando}>
                      <Send className="h-4 w-4" /> Enviar
                    </Button>
                  </span>
                </div>
              </div>
              <AIFactualityLegend />
            </>
          ) : (
            <EmptyState
              icon={Scale}
              title="Selecione ou crie uma análise"
              message="A Sala Jurídica é a porta de entrada conversacional do EJC."
            />
          )}
        </section>

        {/* ── Direita: anexos + estado jurídico ────────────────────────── */}
        <aside className="space-y-3">
          <div className="rounded-xl border border-gray-200 bg-white p-3 shadow-sm">
            <p className="mb-2 flex items-center gap-2 text-sm font-semibold">
              <UploadCloud className="h-4 w-4" /> Documentos ({ativa?.anexos?.length ?? 0})
            </p>
            {(ativa?.anexos ?? []).map((a) => (
              <p key={a.id} className="mb-1 flex items-center justify-between text-xs">
                <span className="truncate">{a.nome_original}</span>
                <Badge tone={a.ocr_utilizado ? "green" : "slate"}>
                  {a.ocr_utilizado ? "OCR" : "texto"}
                </Badge>
              </p>
            ))}
            {(ativa?.anexos ?? []).length === 0 && (
              <p className="text-xs text-gray-400">Nenhum documento anexado.</p>
            )}
          </div>

          <div className="rounded-xl border border-gray-200 bg-white p-3 shadow-sm">
            <p className="mb-2 text-sm font-semibold">
              Estado jurídico{" "}
              {ativa?.estado ? (
                <Badge tone="green">v{ativa.estado.versao}</Badge>
              ) : (
                <Badge tone="slate">vazio</Badge>
              )}
            </p>
            <div className="mb-2 flex flex-wrap gap-1">
              {ABAS_ESTADO.map((aba) => (
                <button
                  key={aba}
                  onClick={() => setAbaEstado(aba)}
                  className={cn(
                    "rounded px-2 py-0.5 text-[11px] font-semibold",
                    abaEstado === aba
                      ? "bg-primary-100 text-primary-800"
                      : "bg-gray-100 text-gray-500 hover:bg-gray-200",
                  )}
                >
                  {aba}
                </button>
              ))}
            </div>
            {(estadoAtual[abaEstado] ?? []).length === 0 ? (
              <p className="text-xs text-gray-400">
                Sem itens em “{abaEstado}”. A curadoria fina é do advogado (PATCH
                /estado); fontes acumulam automaticamente a cada resposta.
              </p>
            ) : (
              (estadoAtual[abaEstado] ?? []).map((item, i) => (
                <div key={i} className="mb-1 rounded border border-gray-100 p-2 text-xs">
                  <span
                    className={cn(
                      "mr-1 rounded px-1.5 py-0.5 text-[10px] font-bold",
                      CLASSIFICACAO_COR[String(item.classificacao ?? "")] ??
                        "bg-gray-100 text-gray-600",
                    )}
                  >
                    {String(item.classificacao ?? item.nivel ?? item.tipo ?? abaEstado)}
                  </span>
                  {String(
                    item.texto ?? item.descricao ?? item.nome ?? item.titulo ?? item.evento ?? "",
                  )}
                </div>
              ))
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
