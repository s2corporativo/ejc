import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  Gavel,
  RefreshCw,
  Scale,
  Sparkles,
} from "lucide-react";
import api from "../../lib/api";
import { toast } from "../../components/Toast";
import { Alert, Badge, Button, Card, Skeleton } from "../../components/UI";

type AnyRecord = Record<string, any>;

type Props = {
  caseId: string;
  onNovo?: () => void;
};

function erroTexto(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response
    ?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail === "object") {
    const mensagem = (detail as { mensagem?: unknown }).mensagem;
    if (typeof mensagem === "string" && mensagem.trim()) return mensagem;
  }
  return fallback;
}

function rotulo(value: unknown): string {
  if (value == null || value === "") return "—";
  if (["string", "number"].includes(typeof value)) return String(value);
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (typeof value === "object") {
    const item = value as AnyRecord;
    for (const key of ["titulo", "nome", "descricao", "acao", "valor", "texto"]) {
      if (typeof item[key] === "string" && item[key]) return item[key];
    }
  }
  return JSON.stringify(value);
}

function Lista({ itens }: { itens?: unknown[] }) {
  if (!itens?.length) {
    return <p className="text-sm text-slate-500">Nenhum item identificado.</p>;
  }
  return (
    <ul className="space-y-2">
      {itens.map((item, index) => (
        <li
          key={`${rotulo(item)}-${index}`}
          className="text-sm text-slate-700 dark:text-slate-200"
        >
          <span className="mr-2 text-slate-400">•</span>
          {rotulo(item)}
        </li>
      ))}
    </ul>
  );
}

function Secao({
  titulo,
  children,
  aberta = false,
}: {
  titulo: string;
  children: React.ReactNode;
  aberta?: boolean;
}) {
  return (
    <details
      open={aberta}
      className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
    >
      <summary className="cursor-pointer select-none text-sm font-semibold text-slate-900 dark:text-slate-100">
        {titulo}
      </summary>
      <div className="mt-4">{children}</div>
    </details>
  );
}

export default function DossieJuridico({ caseId, onNovo }: Props) {
  const navigate = useNavigate();
  const [dossie, setDossie] = useState<AnyRecord | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [aprovando, setAprovando] = useState(false);
  const [aprovado, setAprovado] = useState(false);
  const [planoPeca, setPlanoPeca] = useState<AnyRecord | null>(null);
  const [preparando, setPreparando] = useState(false);
  const [gerando, setGerando] = useState(false);
  const [termoInicial, setTermoInicial] = useState("");
  const [termoConfirmado, setTermoConfirmado] = useState(false);
  const [resultadoPeca, setResultadoPeca] = useState<AnyRecord | null>(null);
  const [gatePeca, setGatePeca] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    setLoading(true);
    setErro(null);
    setAprovado(false);
    setPlanoPeca(null);
    setResultadoPeca(null);
    try {
      const { data } = await api.post("/entrada/analisar", undefined, {
        params: { case_id: caseId },
      });
      setDossie(data);
    } catch (err) {
      setErro(erroTexto(err, "Não foi possível gerar o dossiê jurídico."));
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const partes = (dossie?.identificacao?.partes ?? []) as AnyRecord[];
  const tipos = (dossie?.conteudo_identificado?.tipos ?? []) as string[];
  const matriz = (dossie?.provas?.matriz_fato_prova_tese ?? []) as AnyRecord[];
  const perguntas = (dossie?.lacunas?.perguntas ?? []) as AnyRecord[];
  const plano = dossie?.plano_juridico ?? {};
  const estimativa = dossie?.estimativa_sucesso;
  const honorario = dossie?.honorarios_sugeridos?.faixas?.recomendado?.valor;
  const checklist = useMemo(
    () => (planoPeca?.checklist?.itens ?? []) as AnyRecord[],
    [planoPeca],
  );

  const aprovarPlano = async () => {
    const endpoint = dossie?.snapshot?.aprovar_endpoint;
    if (!endpoint) return;
    setAprovando(true);
    try {
      await api.post(endpoint);
      setAprovado(true);
      toast.success("Plano jurídico aprovado e congelado no histórico do caso.");
    } catch (err) {
      toast.error(erroTexto(err, "Não foi possível aprovar o plano jurídico."));
    } finally {
      setAprovando(false);
    }
  };

  const prepararPeca = async () => {
    setPreparando(true);
    setGatePeca(null);
    try {
      const { data } = await api.post(`/cases/${caseId}/motor-peca/analisar`, {
        texto: dossie?.fatos?.sumario || undefined,
        incluir_motivacao_ia: true,
      });
      setPlanoPeca(data);
    } catch (err) {
      setGatePeca(erroTexto(err, "Não foi possível preparar o Motor de Peça."));
    } finally {
      setPreparando(false);
    }
  };

  const gerarPeca = async () => {
    const pecaCodigo = planoPeca?.peca_principal;
    if (!pecaCodigo) {
      setGatePeca("Confirme uma peça cabível antes de prosseguir.");
      return;
    }
    if (!termoInicial || !termoConfirmado) {
      setGatePeca(
        "Informe e confirme o termo inicial. O EJC não presume prazo fatal.",
      );
      return;
    }
    setGerando(true);
    setGatePeca(null);
    try {
      const { data } = await api.post(`/cases/${caseId}/motor-peca/gerar`, {
        peca_codigo: pecaCodigo,
        rito_codigo: planoPeca?.rito?.codigo || null,
        termo_inicial: termoInicial,
        termo_inicial_confirmado: true,
        descricao_fatos: dossie?.fatos?.sumario || null,
        pedidos: Array.isArray(plano?.pedidos_possiveis)
          ? plano.pedidos_possiveis.map(rotulo).join("; ")
          : null,
        area_direito: dossie?.identificacao?.area_canonica || null,
        nivel_inteligencia: "alto",
      });
      setResultadoPeca(data);
      toast.success("Peça gerada como rascunho para revisão jurídica.");
    } catch (err) {
      setGatePeca(
        erroTexto(err, "O Motor de Peça bloqueou a geração. Revise os requisitos."),
      );
    } finally {
      setGerando(false);
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-5xl space-y-4 py-4">
        <Skeleton className="h-24" />
        <Skeleton className="h-40" />
        <Skeleton className="h-56" />
      </div>
    );
  }

  if (erro || !dossie) {
    return (
      <div className="mx-auto max-w-4xl space-y-4 py-4">
        <Alert variant="danger" title="Dossiê indisponível">
          {erro || "Resposta vazia."}
        </Alert>
        <Button
          variant="secondary"
          onClick={() => void carregar()}
          icon={<RefreshCw className="h-4 w-4" />}
        >
          Tentar novamente
        </Button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-ai-600" />
            <h2 className="text-xl font-semibold text-slate-950 dark:text-white">
              Dossiê Jurídico
            </h2>
            <Badge tone="purple">rascunho</Badge>
          </div>
          <p className="mt-1 max-w-3xl text-sm text-slate-500">{dossie.aviso}</p>
        </div>
        <div className="flex gap-2">
          {onNovo && (
            <Button variant="ghost" onClick={onNovo}>
              Nova entrada
            </Button>
          )}
          <Button variant="secondary" onClick={() => navigate(`/casos/${caseId}`)}>
            Abrir caso
          </Button>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Card className="p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Conteúdo</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {tipos.map((tipo) => (
              <Badge key={tipo} tone="slate">{tipo.replace(/_/g, " ")}</Badge>
            ))}
          </div>
        </Card>
        <Card className="p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Cliente e ramo</p>
          <p className="mt-2 font-medium text-slate-900 dark:text-white">
            {dossie.identificacao?.cliente?.nome || "Cliente não identificado"}
          </p>
          <p className="text-sm text-slate-500">{dossie.identificacao?.ramo || "Ramo a confirmar"}</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Honorário sugerido</p>
          <p className="mt-2 text-lg font-semibold text-slate-900 dark:text-white">
            {typeof honorario === "number"
              ? honorario.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })
              : "Sem base OAB suficiente"}
          </p>
          <p className="text-xs text-slate-500">Referência determinística; confirmação do advogado.</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Estimativa de sucesso</p>
          <p className="mt-2 text-lg font-semibold text-slate-900 dark:text-white">
            {typeof estimativa?.percentual === "number"
              ? `${estimativa.percentual}%`
              : "Sem base verificável"}
          </p>
          <p className="text-xs text-slate-500">Não é promessa de resultado.</p>
        </Card>
      </div>

      {estimativa?.base_estimativa && (
        <Alert variant="info" title="Base da estimativa">
          {estimativa.base_estimativa}
        </Alert>
      )}

      <Secao titulo="Cliente, partes e identificação" aberta>
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <p className="mb-2 text-xs font-semibold uppercase text-slate-400">Partes</p>
            <Lista itens={partes.map((p) => `${p.tipo || p.papel_processual || "parte"}: ${p.nome}`)} />
          </div>
          <div className="space-y-1 text-sm text-slate-700 dark:text-slate-200">
            <p><strong>Área:</strong> {rotulo(dossie.identificacao?.area_canonica)}</p>
            <p><strong>Subramo:</strong> {rotulo(dossie.identificacao?.subramo)}</p>
            <p><strong>Processo:</strong> {rotulo(dossie.identificacao?.numero_processo)}</p>
            <p><strong>Tribunal:</strong> {rotulo(dossie.identificacao?.tribunal)}</p>
            <p><strong>Fase:</strong> {rotulo(dossie.identificacao?.fase)}</p>
          </div>
        </div>
      </Secao>

      <Secao titulo="Fatos e cronologia" aberta>
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700 dark:text-slate-200">
          {dossie.fatos?.sumario || "Síntese ainda não disponível."}
        </p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div><p className="mb-2 text-xs font-semibold uppercase text-slate-400">Pontos fortes</p><Lista itens={dossie.fatos?.pontos_fortes} /></div>
          <div><p className="mb-2 text-xs font-semibold uppercase text-slate-400">Pontos fracos</p><Lista itens={dossie.fatos?.pontos_fracos} /></div>
        </div>
      </Secao>

      <Secao titulo="Provas e matriz Fato × Prova × Tese" aberta>
        <div className="space-y-3">
          {matriz.length === 0 ? (
            <p className="text-sm text-slate-500">A análise ainda não produziu correlações suficientes.</p>
          ) : (
            matriz.map((linha, index) => (
              <Card key={index} className="p-3">
                <p className="text-sm"><strong>Fato:</strong> {rotulo(linha.fato)}</p>
                <p className="mt-1 text-sm">
                  <strong>Prova:</strong> {rotulo(linha.prova)}{" "}
                  {linha.prova_ja_disponivel ? <Badge tone="green">disponível</Badge> : <Badge tone="amber">a obter</Badge>}
                </p>
                <p className="mt-1 text-sm"><strong>Tese(s):</strong> {(linha.teses_relacionadas || []).join("; ") || "correlação a confirmar"}</p>
                <p className="mt-2 text-xs text-slate-400">{linha.observacao}</p>
              </Card>
            ))
          )}
        </div>
      </Secao>

      <Secao titulo="Lacunas e perguntas ao advogado">
        {perguntas.length === 0 ? (
          <Alert variant="success">Nenhuma lacuna estruturada adicional foi identificada nesta rodada.</Alert>
        ) : (
          <div className="space-y-3">
            {perguntas.map((item, index) => (
              <Card key={index} className="p-3">
                <p className="text-sm font-medium text-slate-900 dark:text-white">{item.pergunta}</p>
                <p className="mt-1 text-xs text-slate-500">{item.motivo}</p>
              </Card>
            ))}
          </div>
        )}
      </Secao>

      <Secao titulo="Teses, fundamentos e riscos">
        <p className="mb-2 text-xs font-semibold uppercase text-slate-400">Teses analisadas</p>
        <Lista itens={dossie.analise_juridica?.teses_analisadas} />
        <p className="mb-2 mt-4 text-xs font-semibold uppercase text-slate-400">Teses do banco</p>
        <Lista itens={dossie.analise_juridica?.teses_do_banco} />
        <p className="mb-2 mt-4 text-xs font-semibold uppercase text-slate-400">Riscos</p>
        <Lista itens={dossie.analise_juridica?.riscos} />
      </Secao>

      <Secao titulo="Contradições e leitura adversarial">
        <Alert variant="warning" title="Hipóteses para revisão">
          {dossie.contradicoes_e_adversarial?.observacao}
        </Alert>
        <div className="mt-3">
          <Lista itens={dossie.contradicoes_e_adversarial?.falhas_da_parte_contraria} />
        </div>
        {dossie.contradicoes_e_adversarial?.critica_adversarial?.relatorio && (
          <pre className="mt-4 whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-sm text-slate-700 dark:bg-slate-950 dark:text-slate-200">
            {dossie.contradicoes_e_adversarial.critica_adversarial.relatorio}
          </pre>
        )}
      </Secao>

      <Secao titulo="Honorários sugeridos">
        <Alert variant="info">{dossie.honorarios_sugeridos?.aviso}</Alert>
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          {(["minimo_etico", "recomendado", "estrategico"] as const).map((faixa) => {
            const item = dossie.honorarios_sugeridos?.faixas?.[faixa];
            return (
              <Card key={faixa} className="p-3">
                <p className="text-xs font-semibold uppercase text-slate-400">{faixa.replace(/_/g, " ")}</p>
                <p className="mt-1 font-semibold">
                  {typeof item?.valor === "number"
                    ? item.valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })
                    : "—"}
                </p>
                <p className="mt-1 text-xs text-slate-500">{item?.memoria_calculo}</p>
              </Card>
            );
          })}
        </div>
      </Secao>

      <Secao titulo="Plano jurídico" aberta>
        <div className="grid gap-4 md:grid-cols-2">
          <div><p className="mb-2 text-xs font-semibold uppercase text-slate-400">Tese principal</p><p className="text-sm">{rotulo(plano.tese_principal)}</p></div>
          <div><p className="mb-2 text-xs font-semibold uppercase text-slate-400">Pedidos possíveis</p><Lista itens={plano.pedidos_possiveis} /></div>
          <div><p className="mb-2 text-xs font-semibold uppercase text-slate-400">Próximos passos</p><Lista itens={plano.proximos_passos} /></div>
          <div><p className="mb-2 text-xs font-semibold uppercase text-slate-400">Argumentos adversos prováveis</p><Lista itens={plano.argumentos_adversos_provaveis} /></div>
        </div>
        <div className="mt-5 flex flex-wrap gap-2">
          {!aprovado ? (
            <Button
              variant="primary"
              onClick={aprovarPlano}
              disabled={aprovando}
              icon={<CheckCircle2 className="h-4 w-4" />}
            >
              {aprovando ? "Aprovando…" : "Aprovar plano jurídico"}
            </Button>
          ) : (
            <Badge tone="green">Plano aprovado e congelado</Badge>
          )}
          {aprovado && (
            <Button
              variant="ai"
              onClick={prepararPeca}
              disabled={preparando}
              icon={<Gavel className="h-4 w-4" />}
            >
              {preparando ? "Preparando…" : "Gerar peça"}
            </Button>
          )}
        </div>
      </Secao>

      {aprovado && planoPeca && (
        <Card className="space-y-4 border-ai-200 p-5">
          <div className="flex items-center gap-2">
            <Scale className="h-5 w-5 text-ai-600" />
            <h3 className="font-semibold">Motor de Peça</h3>
          </div>
          <p className="text-sm"><strong>Peça indicada:</strong> {rotulo(planoPeca.peca_principal)}</p>
          <p className="text-sm"><strong>Rito:</strong> {rotulo(planoPeca.rito?.nome || planoPeca.rito?.codigo)}</p>
          {!planoPeca.checklist?.pronto && (
            <Alert variant="warning" title="Checklist bloqueante pendente">
              <Lista itens={checklist.filter((item) => !item.ok && !item.presente)} />
            </Alert>
          )}
          <div className="grid gap-3 md:grid-cols-[220px_1fr] md:items-end">
            <label className="text-sm font-medium text-slate-700 dark:text-slate-200">
              Termo inicial do prazo
              <input
                type="date"
                value={termoInicial}
                onChange={(event) => {
                  setTermoInicial(event.target.value);
                  setTermoConfirmado(false);
                }}
                className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 dark:border-slate-600 dark:bg-slate-900"
              />
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
              <input
                type="checkbox"
                checked={termoConfirmado}
                onChange={(event) => setTermoConfirmado(event.target.checked)}
              />
              Confirmo que revisei o termo inicial informado
            </label>
          </div>
          {gatePeca && (
            <Alert variant="warning" title="Geração bloqueada">
              <AlertTriangle className="mr-1 inline h-4 w-4" />
              {gatePeca}
            </Alert>
          )}
          <Button
            variant="primary"
            onClick={gerarPeca}
            disabled={gerando || !planoPeca.checklist?.pronto}
            icon={<FileText className="h-4 w-4" />}
          >
            {gerando ? "Gerando rascunho…" : "Gerar rascunho da peça"}
          </Button>
        </Card>
      )}

      {resultadoPeca && (
        <Alert variant="success" title="Peça gerada para revisão">
          O Motor de Peça concluiu a geração como rascunho. Prazo confirmado:{" "}
          {resultadoPeca.deadline?.data_prazo || "—"}. A revisão humana e os
          gates de citação continuam obrigatórios.
        </Alert>
      )}
    </div>
  );
}
