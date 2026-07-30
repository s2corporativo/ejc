import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Eye,
  FileDown,
  FolderOpen,
  PenLine,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Wrench,
} from "lucide-react";

import CaseFilterChip from "../components/CaseFilterChip";
import Markdown from "../components/Markdown";
import { toast } from "../components/Toast";
import {
  Badge,
  Button,
  EmptyState,
  Modal,
  PageHeader,
  Spinner,
  StatusBadge,
  fmtDate,
} from "../components/UI";
import { useCasoFiltro } from "../contexts/useCasoFiltro";
import api from "../lib/api";
import type { LegalDoc, Paged } from "../types";
import PecasLegacy from "./PecasLegacy";

const STATUS_CONFERIDOS = new Set(["aprovada", "final", "protocolada"]);

function detalheErro(e: any, fallback: string): string {
  const detail = e?.response?.data?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (detail && typeof detail === "object") {
    return detail.mensagem ?? JSON.stringify(detail).slice(0, 300);
  }
  return fallback;
}

function nomeArquivo(titulo: string): string {
  const seguro = titulo
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9 _.-]/g, "")
    .trim();
  return seguro || "minuta-juridica";
}

function estadoValidacao(doc: LegalDoc) {
  const v = doc.validacao_juridica;
  if (!v || v.status === "sem_validacao") {
    return { texto: "Validação será executada no ato", tone: "slate" as const };
  }
  if (v.apto_fluxo) {
    return {
      texto: `Validação apta${v.score != null ? ` · ${v.score}/100` : ""}`,
      tone: "green" as const,
    };
  }
  if (v.status === "score_baixo") {
    return {
      texto: `Score insuficiente${v.score != null ? ` · ${v.score}/100` : ""}`,
      tone: "red" as const,
    };
  }
  return {
    texto: `Validação pendente${v.score != null ? ` · ${v.score}/100` : ""}`,
    tone: "amber" as const,
  };
}

/**
 * Entrada principal da Parte 10.
 *
 * A tela histórica permanece disponível abaixo, mas o caminho operacional normal
 * concentra PDF, leitura e confirmação do advogado em uma única fila. Isso evita
 * quebrar templates, Visual Law, triagem e ferramentas já existentes enquanto a
 * experiência principal deixa de exigir quatro atos redundantes.
 */
export default function Pecas() {
  const { casoFiltro, casoFiltroNome, removerFiltro } = useCasoFiltro();
  const [data, setData] = useState<Paged<LegalDoc> | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState(false);
  const [detalhe, setDetalhe] = useState<LegalDoc | null>(null);
  const [abrindo, setAbrindo] = useState(false);
  const [assinatura, setAssinatura] = useState<{
    doc: LegalDoc;
    observacoes: string;
  } | null>(null);
  const [confirmando, setConfirmando] = useState(false);
  const [baixando, setBaixando] = useState<string | null>(null);
  const [mostrarAvancado, setMostrarAvancado] = useState(false);
  const topoRef = useRef<HTMLDivElement>(null);

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro(false);
    try {
      const resposta = await api.get<Paged<LegalDoc>>("/legal-docs/", {
        params: { page_size: 100, case_id: casoFiltro },
      });
      setData(resposta.data);
    } catch (e: any) {
      setErro(true);
      toast.error(detalheErro(e, "Falha ao carregar as minutas jurídicas"));
    } finally {
      setCarregando(false);
    }
  }, [casoFiltro]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const documentos = useMemo(
    () => (data && Array.isArray(data.data) ? data.data : []),
    [data],
  );

  const aguardando = useMemo(
    () =>
      documentos.filter(
        (doc) => doc.ai_generated && !STATUS_CONFERIDOS.has(doc.status),
      ),
    [documentos],
  );

  const demais = useMemo(
    () =>
      documentos.filter(
        (doc) => !(doc.ai_generated && !STATUS_CONFERIDOS.has(doc.status)),
      ),
    [documentos],
  );

  const abrirDetalhe = async (doc: LegalDoc) => {
    setAbrindo(true);
    try {
      const resposta = await api.get<LegalDoc>(`/legal-docs/${doc.id}`);
      setDetalhe(resposta.data);
    } catch (e: any) {
      toast.error(detalheErro(e, "Falha ao abrir a minuta"));
    } finally {
      setAbrindo(false);
    }
  };

  const baixarMinuta = async (doc: LegalDoc) => {
    if (baixando) return;
    setBaixando(doc.id);
    try {
      const resposta = await api.get(`/legal-docs/${doc.id}/pdf-minuta`, {
        responseType: "blob",
      });
      const url = URL.createObjectURL(resposta.data);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${nomeArquivo(doc.titulo)}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      let mensagem = "Falha ao gerar o PDF da minuta";
      if (e?.response?.data instanceof Blob) {
        try {
          const corpo = JSON.parse(await e.response.data.text());
          mensagem =
            typeof corpo?.detail === "string"
              ? corpo.detail
              : (corpo?.detail?.mensagem ?? mensagem);
        } catch {
          // mantém a mensagem operacional segura
        }
      } else {
        mensagem = detalheErro(e, mensagem);
      }
      toast.error(mensagem);
    } finally {
      setBaixando(null);
    }
  };

  const conferirEAssinar = async () => {
    if (!assinatura || confirmando) return;
    setConfirmando(true);
    try {
      await api.patch(`/legal-docs/${assinatura.doc.id}/conferir-assinar`, {
        confirmado: true,
        observacoes: assinatura.observacoes.trim() || null,
      });
      toast.success(
        "Conferência registrada. A minuta foi liberada para assinatura e uso oficial.",
      );
      setAssinatura(null);
      await carregar();
    } catch (e: any) {
      toast.error(
        detalheErro(
          e,
          "A minuta não foi liberada. Corrija os pontos indicados e tente novamente.",
        ),
      );
    } finally {
      setConfirmando(false);
    }
  };

  const bloquearFluxoLegado = (event: React.MouseEvent<HTMLDivElement>) => {
    const alvo = event.target as HTMLElement;
    const botao = alvo.closest("button");
    const rotulo = botao?.textContent?.replace(/\s+/g, " ").trim() ?? "";
    const acaoAntiga =
      rotulo === "Revisar" ||
      rotulo === "Revisar e Aprovar" ||
      rotulo === "Aprovar peça" ||
      rotulo === "Aprovar revisão";
    if (!acaoAntiga) return;

    event.preventDefault();
    event.stopPropagation();
    toast.info(
      'Use a ação única "Conferir e assinar" no painel principal desta página.',
    );
    topoRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div ref={topoRef}>
      <PageHeader
        title="Minutas e Peças Jurídicas"
        subtitle={`${data?.total ?? 0} documento(s) · fluxo de conferência em ato único`}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={carregar} disabled={carregando}>
              <RefreshCw size={15} className={carregando ? "animate-spin" : ""} />
              Atualizar
            </Button>
            <Button
              variant="secondary"
              onClick={() => setMostrarAvancado((atual) => !atual)}
            >
              <Wrench size={15} />
              Ferramentas avançadas
              {mostrarAvancado ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </Button>
          </div>
        }
      />

      {casoFiltro && (
        <div className="mb-4">
          <CaseFilterChip nome={casoFiltroNome} onRemove={removerFiltro} />
        </div>
      )}

      <div className="mb-5 rounded-xl border border-primary-100 bg-primary-50/60 p-4">
        <div className="flex items-start gap-3">
          <div className="rounded-lg bg-white p-2 text-primary-700 shadow-sm">
            <PenLine size={20} />
          </div>
          <div className="min-w-0">
            <h2 className="font-semibold text-navy">Fluxo principal da minuta</h2>
            <p className="mt-1 text-sm text-slate-600">
              A IA entrega a minuta completa. O PDF pode ser baixado imediatamente
              com identificação de minuta. Em um único ato, o advogado confere,
              assume a responsabilidade técnica e libera a versão para uso oficial.
              Score, fontes, jurisprudência e trilha de auditoria continuam ativos.
            </p>
          </div>
        </div>
      </div>

      {carregando && !data ? (
        <Spinner />
      ) : erro && !data ? (
        <EmptyState
          title="Não foi possível carregar as minutas"
          message="Verifique a conexão e tente novamente. Nenhum dado foi alterado."
          action={
            <Button variant="primary" onClick={carregar}>
              Tentar novamente
            </Button>
          }
        />
      ) : documentos.length === 0 ? (
        <EmptyState
          title={casoFiltro ? "Nenhuma minuta neste caso" : "Nenhuma peça cadastrada"}
          message={
            casoFiltro
              ? "Abra as ferramentas avançadas para gerar uma peça vinculada ao caso, ou remova o filtro para ver todas."
              : "Abra as ferramentas avançadas para gerar a primeira minuta por IA, template ou edição manual."
          }
          action={
            <Button variant="primary" onClick={() => setMostrarAvancado(true)}>
              <Sparkles size={15} /> Abrir geração de peças
            </Button>
          }
        />
      ) : (
        <div className="space-y-7">
          <section>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="text-sm font-semibold uppercase tracking-wide text-navy">
                  A conferir e assinar
                </h2>
                <p className="text-xs text-slate-500">
                  {aguardando.length} minuta(s) gerada(s) com auxílio de IA
                </p>
              </div>
              <Badge tone={aguardando.length ? "amber" : "green"}>
                {aguardando.length ? "Ação do advogado" : "Fila em dia"}
              </Badge>
            </div>

            {aguardando.length === 0 ? (
              <div className="card flex items-center gap-3 p-5 text-sm text-success-700">
                <CheckCircle2 size={20} />
                Nenhuma minuta de IA aguarda conferência.
              </div>
            ) : (
              <div className="grid gap-3 xl:grid-cols-2">
                {aguardando.map((doc) => (
                  <PecaCard
                    key={doc.id}
                    doc={doc}
                    principal
                    baixando={baixando === doc.id}
                    abrindo={abrindo}
                    onAbrir={() => abrirDetalhe(doc)}
                    onBaixar={() => baixarMinuta(doc)}
                    onConferir={() =>
                      setAssinatura({ doc, observacoes: "" })
                    }
                  />
                ))}
              </div>
            )}
          </section>

          <section>
            <div className="mb-3">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-navy">
                Demais documentos
              </h2>
              <p className="text-xs text-slate-500">
                Peças manuais, conferidas, finais ou protocoladas
              </p>
            </div>
            <div className="grid gap-3 xl:grid-cols-2">
              {demais.map((doc) => (
                <PecaCard
                  key={doc.id}
                  doc={doc}
                  baixando={baixando === doc.id}
                  abrindo={abrindo}
                  onAbrir={() => abrirDetalhe(doc)}
                  onBaixar={() => baixarMinuta(doc)}
                />
              ))}
            </div>
          </section>
        </div>
      )}

      {mostrarAvancado && (
        <section className="mt-10 border-t border-slate-200 pt-6">
          <div className="mb-4 rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
            <strong>Ferramentas avançadas preservadas:</strong> geração por IA,
            templates, triagem, Visual Law, DOCX, impressão, auditoria e protocolo.
            As antigas ações separadas de revisão ficam bloqueadas; use o ato único
            no painel principal.
          </div>
          <div onClickCapture={bloquearFluxoLegado} data-parte10-legado>
            <PecasLegacy />
          </div>
        </section>
      )}

      <Modal
        open={!!detalhe}
        onClose={() => setDetalhe(null)}
        title={detalhe?.titulo ?? "Minuta"}
        wide
      >
        {detalhe && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <StatusBadge value={detalhe.status} />
              {detalhe.ai_generated ? (
                <Badge tone={detalhe.human_reviewed ? "green" : "amber"}>
                  {detalhe.human_reviewed
                    ? "IA · conferida pelo advogado"
                    : "IA · minuta a conferir"}
                </Badge>
              ) : (
                <Badge tone="slate">Elaboração manual</Badge>
              )}
              <span className="text-slate-400">
                v{detalhe.versao}.0 · {fmtDate(detalhe.created_at)}
              </span>
            </div>
            {detalhe.case_id && (
              <Link
                to={`/casos/${detalhe.case_id}`}
                className="inline-flex items-center gap-1 text-xs text-primary-700 hover:underline"
              >
                <FolderOpen size={13} /> Abrir caso vinculado
              </Link>
            )}
            {detalhe.ai_generated && !detalhe.human_reviewed && (
              <div className="rounded-lg border border-warn-200 bg-warn-50 p-3 text-xs text-warn-800">
                <strong>Minuta gerada por IA.</strong> Confira fatos, documentos,
                prazos, fundamentos, jurisprudência e pedidos antes do uso oficial.
              </div>
            )}
            <Markdown source={detalhe.conteudo} className="text-sm text-slate-700" />
          </div>
        )}
      </Modal>

      <Modal
        open={!!assinatura}
        onClose={() => !confirmando && setAssinatura(null)}
        title="Conferir e assinar minuta"
      >
        <div className="space-y-4">
          <div className="rounded-lg border border-primary-100 bg-primary-50 p-3 text-sm text-slate-700">
            <p>
              Ao confirmar, você declara ter conferido a versão{" ""}
              <strong>v{assinatura?.doc.versao}.0</strong> de{" ""}
              <strong>{assinatura?.doc.titulo}</strong> e assume a responsabilidade
              profissional pelo seu uso.
            </p>
            <p className="mt-2 text-xs text-slate-500">
              O EJC validará a versão atual, verificará score e jurisprudência,
              registrará usuário, data, versão e log técnico. A assinatura digital e
              o protocolo no PJe/eproc permanecem atos externos quando aplicáveis.
            </p>
          </div>

          <div>
            <label className="label">Observações da conferência (opcional)</label>
            <textarea
              className="input min-h-[110px]"
              placeholder="Registre apenas ajustes, ressalvas ou conferências relevantes."
              value={assinatura?.observacoes ?? ""}
              onChange={(event) =>
                assinatura &&
                setAssinatura({
                  ...assinatura,
                  observacoes: event.target.value,
                })
              }
            />
          </div>

          <div className="flex justify-end gap-2">
            <Button
              variant="secondary"
              onClick={() => setAssinatura(null)}
              disabled={confirmando}
            >
              Cancelar
            </Button>
            <Button
              variant="primary"
              onClick={conferirEAssinar}
              disabled={confirmando}
            >
              <ShieldCheck size={15} />
              {confirmando
                ? "Validando e registrando..."
                : "Confirmo a conferência e assino"}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

function PecaCard({
  doc,
  principal = false,
  baixando,
  abrindo,
  onAbrir,
  onBaixar,
  onConferir,
}: {
  doc: LegalDoc;
  principal?: boolean;
  baixando: boolean;
  abrindo: boolean;
  onAbrir: () => void;
  onBaixar: () => void;
  onConferir?: () => void;
}) {
  const validacao = estadoValidacao(doc);
  return (
    <article
      className={`card p-4 ${
        principal ? "border-l-4 border-l-warn-400" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="break-words font-medium text-navy">{doc.titulo}</h3>
          <p className="mt-1 text-xs capitalize text-slate-400">
            {doc.tipo_peca.replace(/_/g, " ")} · v{doc.versao}.0 ·{" "}
            {fmtDate(doc.created_at)}
          </p>
        </div>
        <StatusBadge value={doc.status} />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        {doc.ai_generated ? (
          <Badge tone={doc.human_reviewed ? "green" : "amber"}>
            <Sparkles size={12} />
            {doc.human_reviewed ? "IA conferida" : "Minuta de IA"}
          </Badge>
        ) : (
          <Badge tone="slate">Manual</Badge>
        )}
        <Badge tone={validacao.tone}>{validacao.texto}</Badge>
        {doc.case_id && (
          <Link
            to={`/casos/${doc.case_id}`}
            className="inline-flex items-center gap-1 text-xs text-primary-700 hover:underline"
          >
            <FolderOpen size={12} /> Caso
          </Link>
        )}
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <Button variant="secondary" onClick={onAbrir} disabled={abrindo}>
          <Eye size={14} /> Ler
        </Button>
        <Button variant="secondary" onClick={onBaixar} disabled={baixando}>
          <FileDown size={14} />
          {baixando ? "Gerando..." : "PDF da minuta"}
        </Button>
        {onConferir && (
          <Button variant="primary" onClick={onConferir}>
            <ShieldCheck size={14} /> Conferir e assinar
          </Button>
        )}
      </div>
    </article>
  );
}
