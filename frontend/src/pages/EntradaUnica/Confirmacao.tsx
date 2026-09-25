// Tela B da Entrada Única (/entrada, mesmo estado de rota): "Confira e
// confirme". Tudo editável, nada obrigatório de digitar; blocos de conflito,
// duplicado e responsável aparecem POR EXCEÇÃO (wireframe da seção 3 de
// docs/DESENHO_BLOCO3_TELAS.md).
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Search, X } from "lucide-react";
import api from "../../lib/api";
import {
  Alert,
  Badge,
  Button,
  Card,
  ConfidenceBadge,
  FieldLabel,
  Input,
  Select,
  Textarea,
  cn,
} from "../../components/UI";
import { AREAS_FALLBACK } from "../../lib/areaCatalog";
import type { Client, User } from "../../types";
import type { Proposta } from "./types";

function Origem({ valor }: { valor?: string | null }) {
  if (!valor) return null;
  return <p className="mt-1 text-[11px] text-slate-400">origem: {valor}</p>;
}

function asLista<T>(payload: unknown): T[] {
  if (Array.isArray(payload)) return payload as T[];
  const data = (payload as { data?: unknown })?.data;
  return Array.isArray(data) ? (data as T[]) : [];
}

function listaParaTexto(itens: string[]): string {
  return itens.join("\n");
}

function textoParaLista(texto: string): string[] {
  // Mantém a última linha vazia enquanto o advogado digita. O schema do
  // backend remove vazios antes de persistir o snapshot confirmado.
  return texto
    .split("\n")
    .map((item) => item.trim())
    .slice(0, 20);
}

const NATUREZAS = [
  ["judicial", "Judicial"],
  ["extrajudicial", "Extrajudicial"],
  ["administrativo", "Administrativo"],
  ["consultoria", "Consultoria"],
] as const;

function nomeCliente(c: Client): string {
  return c.nome || c.razao_social || c.email || c.id;
}

/** Busca de cliente existente — mesmo endpoint paginado do wizard da Sala
 *  Jurídica: GET /clients?search=&page_size=8. */
function BuscaCliente({
  onEscolher,
  onCancelar,
}: {
  onEscolher: (c: Client) => void;
  onCancelar: () => void;
}) {
  const [termo, setTermo] = useState("");
  const [resultados, setResultados] = useState<Client[]>([]);
  const [buscando, setBuscando] = useState(false);

  useEffect(() => {
    const limpo = termo.trim();
    if (limpo.length < 2) {
      setResultados([]);
      return;
    }
    setBuscando(true);
    const t = window.setTimeout(() => {
      api
        // Barra final: sem ela o backend responde 307 para /api/clients/
        // (prefixo legado) — round-trip extra a cada tecla digitada.
        .get("/clients/", { params: { search: limpo, page_size: 8 } })
        .then((r) => setResultados(asLista<Client>(r.data)))
        .catch(() => setResultados([]))
        .finally(() => setBuscando(false));
    }, 350);
    return () => window.clearTimeout(t);
  }, [termo]);

  return (
    <div className="mt-2 space-y-2">
      <div className="relative">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
          aria-hidden="true"
        />
        <Input
          autoFocus
          value={termo}
          onChange={(e) => setTermo(e.target.value)}
          placeholder="Buscar cliente por nome, CPF ou CNPJ…"
          className="pl-9"
          aria-label="Buscar cliente existente"
        />
      </div>
      {buscando && <p className="text-xs text-slate-400">Buscando…</p>}
      {resultados.length > 0 && (
        <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 dark:divide-slate-700 dark:border-slate-600">
          {resultados.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => onEscolher(c)}
                className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-slate-50 dark:hover:bg-slate-700"
              >
                <span className="truncate">{nomeCliente(c)}</span>
                <span className="ml-2 shrink-0 text-xs text-slate-400">
                  {c.tipo}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <Button variant="ghost" size="sm" onClick={onCancelar}>
        Cancelar busca
      </Button>
    </div>
  );
}

export function Confirmacao({
  proposta,
  onChange,
  usuarios,
  criando,
  erro409,
  onCriar,
  onDescartar,
}: {
  proposta: Proposta;
  onChange: (patch: Partial<Proposta>) => void;
  usuarios: User[];
  criando: boolean;
  erro409: string | null;
  onCriar: () => void;
  onDescartar: () => void;
}) {
  const [buscandoCliente, setBuscandoCliente] = useState(false);

  const areaDesconhecida =
    Boolean(proposta.area) &&
    !AREAS_FALLBACK.some((a) => a.slug === proposta.area);

  const precisaConfirmarConflito = proposta.conflitoAlertas.length > 0;
  // Vale TAMBÉM para cliente existente: o servidor devolve 409 com os casos
  // ativos do cliente e exige reconhecimento explícito — restringir a
  // !clienteId deixava o caminho do cliente recorrente num loop de 409.
  const precisaConfirmarDuplicado = proposta.duplicados.length > 0;
  const reconciliacoesComCnj = proposta.reconciliacoes.filter(
    (item) => item.numeroCnj && item.status !== "informacoes_insuficientes",
  );
  const reconciliacaoSelecionada =
    reconciliacoesComCnj.find(
      (item) => item.numeroCnj === proposta.numeroProcesso,
    ) ?? null;
  const precisaEscolherProcesso =
    reconciliacoesComCnj.length > 0 && !proposta.numeroProcesso;
  const bloqueioCasoProtegido =
    reconciliacaoSelecionada?.status === "ja_cadastrado" &&
    reconciliacaoSelecionada.protegido;
  const exigeVinculoExistente =
    reconciliacaoSelecionada?.status === "ja_cadastrado" &&
    !reconciliacaoSelecionada.protegido &&
    Boolean(reconciliacaoSelecionada.caseId) &&
    proposta.reconciliarCaseId !== reconciliacaoSelecionada.caseId;
  const exigeDecisaoCorrespondencia =
    reconciliacaoSelecionada?.status === "provavel_correspondencia" &&
    Boolean(reconciliacaoSelecionada.caseId) &&
    proposta.reconciliarCaseId !== reconciliacaoSelecionada.caseId &&
    !proposta.duplicateConfirmed;

  const podeCriar =
    proposta.confirmoRevisao &&
    (!precisaConfirmarConflito || proposta.conflictConfirmed) &&
    (!precisaConfirmarDuplicado || proposta.duplicateConfirmed) &&
    !precisaEscolherProcesso &&
    !bloqueioCasoProtegido &&
    !exigeVinculoExistente &&
    !exigeDecisaoCorrespondencia &&
    !criando;

  const responsaveis = useMemo(() => {
    const advogados = usuarios.filter(
      (u) =>
        u.is_active !== false &&
        ["superadmin", "admin", "socio", "advogado"].includes(u.role),
    );
    return advogados.length > 0 ? advogados : usuarios;
  }, [usuarios]);

  const atualizarPrazo = (patch: Partial<NonNullable<Proposta["prazo"]>>) => {
    if (!proposta.prazo) return;
    onChange({ prazo: { ...proposta.prazo, ...patch } });
  };

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
          Confira e confirme
        </h2>
        <Badge tone="slate">rascunho</Badge>
      </div>

      {proposta.degradado && (
        <Alert variant="warning">
          A análise por IA está indisponível agora. Os documentos foram
          preservados e classificados pelas regras determinísticas. Preencha o
          que faltar — nada se perdeu.
        </Alert>
      )}

      {proposta.avisos.map((aviso) => (
        <Alert key={aviso} variant="info">
          {aviso}
        </Alert>
      ))}

      {proposta.inteligenciaJuridica && (
        <Card className="border-ai-200 bg-ai-50/40 p-4 dark:border-ai-800 dark:bg-ai-900/20">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                Inteligência jurídica estruturada
              </p>
              <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
                Contrato {proposta.inteligenciaJuridica.versaoContrato} · revisão humana obrigatória
              </p>
            </div>
            <Badge tone={proposta.inteligenciaJuridica.status === "degradado" ? "amber" : "purple"}>
              {proposta.inteligenciaJuridica.status}
            </Badge>
          </div>
          {proposta.inteligenciaJuridica.informacoesFaltantes.length > 0 && (
            <div className="mt-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Pontos que podem mudar a análise
              </p>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-700 dark:text-slate-200">
                {proposta.inteligenciaJuridica.informacoesFaltantes.slice(0, 5).map((item) => (
                  <li key={`${item.pergunta}-${item.motivo}`}>{item.pergunta}</li>
                ))}
              </ul>
            </div>
          )}
          {proposta.inteligenciaJuridica.honorarios.aviso && (
            <p className="mt-3 text-xs text-slate-500">
              {proposta.inteligenciaJuridica.honorarios.aviso}
            </p>
          )}
        </Card>
      )}

      {proposta.reconciliacoes.length > 0 && (
        <Card className="border-slate-200 p-4 dark:border-slate-700">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                Reconciliação processual
              </p>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-300">
                O EJC conferiu os números CNJ antes de criar um caso. Nenhum
                vínculo provável é aplicado sem sua confirmação.
              </p>
            </div>
            <Badge tone="slate">anti-duplicidade</Badge>
          </div>

          <div className="mt-3 space-y-2">
            {proposta.reconciliacoes.map((item, index) => {
              const selecionado =
                Boolean(item.numeroCnj) &&
                proposta.numeroProcesso === item.numeroCnj;
              const vinculado =
                Boolean(item.caseId) &&
                proposta.reconciliarCaseId === item.caseId &&
                selecionado;
              const rotulo =
                item.status === "ja_cadastrado"
                  ? "já cadastrado"
                  : item.status === "provavel_correspondencia"
                    ? "provável correspondência"
                    : item.status === "novo_processo"
                      ? "novo processo"
                      : "informações insuficientes";
              return (
                <div
                  key={`${item.numeroCnj ?? "sem-cnj"}-${index}`}
                  className={cn(
                    "rounded-lg border p-3",
                    selecionado
                      ? "border-primary-300 bg-primary-50/50 dark:border-primary-700 dark:bg-primary-900/10"
                      : "border-slate-200 dark:border-slate-700",
                  )}
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-sm font-medium text-slate-900 dark:text-slate-100">
                          {item.numeroCnj ?? "CNJ não identificado"}
                        </span>
                        <Badge
                          tone={
                            item.status === "ja_cadastrado"
                              ? "slate"
                              : item.status === "provavel_correspondencia"
                                ? "amber"
                                : item.status === "novo_processo"
                                  ? "green"
                                  : "amber"
                          }
                        >
                          {rotulo}
                        </Badge>
                      </div>
                      {item.numeroInterno && (
                        <p className="mt-1 text-sm text-slate-700 dark:text-slate-200">
                          {item.numeroInterno}
                          {item.titulo ? ` — ${item.titulo}` : ""}
                        </p>
                      )}
                      <p className="mt-1 text-xs text-slate-500">
                        {item.mensagem}
                      </p>
                    </div>

                    {item.numeroCnj &&
                      item.status === "novo_processo" && (
                        <Button
                          variant={selecionado ? "primary" : "secondary"}
                          size="sm"
                          onClick={() =>
                            onChange({
                              numeroProcesso: item.numeroCnj ?? "",
                              reconciliarCaseId: null,
                              duplicateConfirmed: false,
                            })
                          }
                        >
                          {selecionado ? "CNJ selecionado" : "Usar no novo caso"}
                        </Button>
                      )}

                    {item.numeroCnj &&
                      item.caseId &&
                      !item.protegido &&
                      item.status === "ja_cadastrado" && (
                        <Button
                          variant={vinculado ? "primary" : "secondary"}
                          size="sm"
                          onClick={() =>
                            onChange({
                              numeroProcesso: item.numeroCnj ?? "",
                              reconciliarCaseId: item.caseId,
                              duplicateConfirmed: true,
                            })
                          }
                        >
                          {vinculado ? "Caso selecionado" : "Usar caso existente"}
                        </Button>
                      )}

                    {item.numeroCnj &&
                      item.caseId &&
                      !item.protegido &&
                      item.status === "provavel_correspondencia" && (
                        <div className="flex flex-wrap gap-2">
                          <Button
                            variant={vinculado ? "primary" : "secondary"}
                            size="sm"
                            onClick={() =>
                              onChange({
                                numeroProcesso: item.numeroCnj ?? "",
                                reconciliarCaseId: item.caseId,
                                duplicateConfirmed: true,
                              })
                            }
                          >
                            {vinculado ? "Vínculo selecionado" : "Vincular a este caso"}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              onChange({
                                numeroProcesso: item.numeroCnj ?? "",
                                reconciliarCaseId: null,
                                duplicateConfirmed: true,
                              })
                            }
                          >
                            Não corresponde — criar novo
                          </Button>
                        </div>
                      )}
                  </div>

                  {item.protegido && item.status === "ja_cadastrado" && (
                    <p className="mt-2 text-xs font-medium text-amber-700 dark:text-amber-300">
                      O caso está protegido. A criação fica bloqueada para este
                      CNJ até revisão da gestão.
                    </p>
                  )}
                </div>
              );
            })}
          </div>

          {reconciliacoesComCnj.length > 1 && (
            <p className="mt-3 text-xs text-slate-500">
              Foram encontrados vários processos no mesmo texto. Selecione o
              CNJ que esta criação deve tratar; os demais permanecem apenas como
              achados deste rascunho.
            </p>
          )}
        </Card>
      )}

      {erro409 && (
        <Alert variant="danger" title="O servidor recusou a criação">
          {erro409} Revise os achados abaixo e confirme os itens exigidos.
        </Alert>
      )}

      {/* Bloco por exceção: conflito de interesses (dever do EOAB) */}
      {precisaConfirmarConflito && (
        <Card className="border-amber-300 bg-amber-50 p-4 dark:border-amber-700 dark:bg-amber-900/20">
          <div className="flex items-start gap-3">
            <AlertTriangle
              className="mt-0.5 h-5 w-5 shrink-0 text-amber-600"
              aria-hidden="true"
            />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-amber-800 dark:text-amber-200">
                CONFLITO DE INTERESSES — {proposta.conflitoAlertas.length}{" "}
                achado{proposta.conflitoAlertas.length > 1 ? "s" : ""}
              </p>
              <ul className="mt-1 list-disc space-y-0.5 pl-4 text-sm text-amber-800 dark:text-amber-200">
                {proposta.conflitoAlertas.map((alerta) => (
                  <li key={alerta}>{alerta}</li>
                ))}
              </ul>
              <label className="mt-2 flex items-center gap-2 text-sm font-medium text-amber-900 dark:text-amber-100">
                <input
                  type="checkbox"
                  checked={proposta.conflictConfirmed}
                  onChange={(e) =>
                    onChange({ conflictConfirmed: e.target.checked })
                  }
                />
                Revisei e não há impedimento
              </label>
            </div>
          </div>
        </Card>
      )}

      <Card className="space-y-5 p-5">
        {/* Cliente */}
        <div>
          <FieldLabel>Cliente</FieldLabel>
          {proposta.clienteId ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium text-slate-800 dark:text-slate-100">
                {proposta.clienteNome || "Cliente selecionado"}
              </span>
              {proposta.clienteJaCadastrada && (
                <Badge tone="green" className="gap-1">
                  <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                  já cadastrada
                  {proposta.clienteCasosAnteriores != null &&
                    ` · ${proposta.clienteCasosAnteriores} caso${proposta.clienteCasosAnteriores === 1 ? "" : "s"} anteriores`}
                </Badge>
              )}
              {proposta.clienteConfianca != null && (
                <ConfidenceBadge value={proposta.clienteConfianca} />
              )}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  // Limpa TODO o contexto do cliente anterior — manter o nome
                  // criaria um homônimo num clique direto em "Criar caso".
                  onChange({
                    clienteId: null,
                    clienteNome: "",
                    clienteJaCadastrada: false,
                    clienteCasosAnteriores: null,
                    clienteConfianca: null,
                    duplicateConfirmed: false,
                  });
                  setBuscandoCliente(true);
                }}
              >
                é outro
              </Button>
            </div>
          ) : (
            <div>
              <div className="flex items-center gap-2">
                <Input
                  value={proposta.clienteNome}
                  onChange={(e) => onChange({ clienteNome: e.target.value })}
                  placeholder="Nome do novo cliente"
                  aria-label="Nome do novo cliente"
                />
                {!buscandoCliente && (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setBuscandoCliente(true)}
                  >
                    Buscar existente
                  </Button>
                )}
              </div>
              {buscandoCliente && (
                <BuscaCliente
                  onEscolher={(c) => {
                    onChange({
                      clienteId: c.id,
                      clienteNome: nomeCliente(c),
                      clienteJaCadastrada: true,
                    });
                    setBuscandoCliente(false);
                  }}
                  onCancelar={() => setBuscandoCliente(false)}
                />
              )}
            </div>
          )}
          <Origem valor={proposta.clienteOrigem} />

          {/* Bloco por exceção: possíveis clientes duplicados */}
          {proposta.duplicados.length > 0 && (
            <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 p-3 dark:border-amber-700 dark:bg-amber-900/20">
              <p className="text-xs font-semibold text-amber-800 dark:text-amber-200">
                {proposta.clienteId
                  ? "Este cliente possui caso ativo — confira se não é o mesmo assunto"
                  : "Cliente possivelmente já cadastrado"}
              </p>
              <ul className="mt-1 space-y-1">
                {proposta.duplicados.map((dup, i) => (
                  <li
                    key={`${dup.clientId ?? dup.rotulo}-${i}`}
                    className="flex items-center justify-between gap-2 text-sm text-amber-900 dark:text-amber-100"
                  >
                    <span className="min-w-0 truncate">{dup.rotulo}</span>
                    {dup.clientId && (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() =>
                          onChange({
                            clienteId: dup.clientId,
                            clienteNome: dup.rotulo,
                            clienteJaCadastrada: true,
                          })
                        }
                      >
                        Usar este cliente
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
              {precisaConfirmarDuplicado && (
                <label className="mt-2 flex items-center gap-2 text-sm font-medium text-amber-900 dark:text-amber-100">
                  <input
                    type="checkbox"
                    checked={proposta.duplicateConfirmed}
                    onChange={(e) =>
                      onChange({ duplicateConfirmed: e.target.checked })
                    }
                  />
                  {proposta.clienteId
                    ? "Conferi os casos ativos e confirmo que este é um caso NOVO"
                    : "Não é o mesmo cliente — cadastrar como novo"}
                </label>
              )}
            </div>
          )}
        </div>

        {/* Área */}
        <div>
          <FieldLabel>Área</FieldLabel>
          <div className="flex items-center gap-2">
            <Select
              value={proposta.area}
              onChange={(e) => onChange({ area: e.target.value })}
              aria-label="Área do caso"
              className="max-w-xs"
            >
              <option value="">Selecionar área…</option>
              {areaDesconhecida && (
                <option value={proposta.area}>{proposta.area}</option>
              )}
              {AREAS_FALLBACK.map((a) => (
                <option key={a.slug} value={a.slug}>
                  {a.nome}
                </option>
              ))}
            </Select>
            {proposta.areaConfianca != null && (
              <ConfidenceBadge value={proposta.areaConfianca} />
            )}
          </div>
        </div>

        {/* Classificação jurídica inicial — toda sugestão continua editável/HITL. */}
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <FieldLabel>Assunto</FieldLabel>
            <div className="flex items-center gap-2">
              <Input
                value={proposta.assunto}
                onChange={(e) => onChange({ assunto: e.target.value })}
                placeholder="Ex.: negativação indevida"
                aria-label="Assunto jurídico"
              />
              {proposta.assuntoConfianca != null && (
                <ConfidenceBadge value={proposta.assuntoConfianca} />
              )}
            </div>
          </div>

          <div>
            <FieldLabel>Natureza da demanda</FieldLabel>
            <Select
              value={proposta.naturezaDemanda}
              onChange={(e) => onChange({ naturezaDemanda: e.target.value })}
              aria-label="Natureza da demanda"
            >
              <option value="">A confirmar…</option>
              {!NATUREZAS.some(([valor]) => valor === proposta.naturezaDemanda) &&
                proposta.naturezaDemanda && (
                  <option value={proposta.naturezaDemanda}>
                    {proposta.naturezaDemanda}
                  </option>
                )}
              {NATUREZAS.map(([valor, rotulo]) => (
                <option key={valor} value={valor}>
                  {rotulo}
                </option>
              ))}
            </Select>
          </div>

          <div>
            <FieldLabel>Possível ação / procedimento</FieldLabel>
            <div className="flex items-center gap-2">
              <Input
                value={proposta.naturezaProvavel}
                onChange={(e) => onChange({ naturezaProvavel: e.target.value })}
                placeholder="Hipótese jurídica a confirmar"
                aria-label="Possível ação ou procedimento"
              />
              {proposta.naturezaConfianca != null && (
                <ConfidenceBadge value={proposta.naturezaConfianca} />
              )}
            </div>
          </div>

          <div>
            <FieldLabel>Prioridade do caso</FieldLabel>
            <Select
              value={proposta.prioridade}
              onChange={(e) =>
                onChange({
                  prioridade: e.target.value as
                    | "baixa"
                    | "media"
                    | "alta"
                    | "critica",
                })
              }
              aria-label="Prioridade do caso"
            >
              <option value="baixa">Baixa</option>
              <option value="media">Média</option>
              <option value="alta">Alta</option>
              <option value="critica">Crítica</option>
            </Select>
          </div>
        </div>

        {(proposta.urgencia !== null || proposta.urgenciaMotivo) && (
          <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-3 dark:border-amber-800 dark:bg-amber-900/10">
            <div className="flex flex-wrap items-center gap-2">
              <FieldLabel>Urgência identificada</FieldLabel>
              <Badge tone={proposta.urgencia ? "amber" : "slate"}>
                {proposta.urgencia === true
                  ? "possível urgência"
                  : proposta.urgencia === false
                    ? "sem urgência aparente"
                    : "a confirmar"}
              </Badge>
              {proposta.urgenciaConfianca != null && (
                <ConfidenceBadge value={proposta.urgenciaConfianca} />
              )}
            </div>
            <Textarea
              value={proposta.urgenciaMotivo}
              onChange={(e) => onChange({ urgenciaMotivo: e.target.value })}
              rows={2}
              placeholder="Motivo da urgência ou ponto que exige conferência"
              aria-label="Motivo da urgência"
            />
            <p className="mt-1 text-[11px] text-slate-400">
              A prioridade acima só é gravada após sua confirmação; a IA não
              torna um caso crítico automaticamente.
            </p>
          </div>
        )}

        {/* Título */}
        <div>
          <FieldLabel>Título</FieldLabel>
          <Input
            value={proposta.titulo}
            onChange={(e) => onChange({ titulo: e.target.value })}
            placeholder="Título do caso"
            aria-label="Título do caso"
          />
        </div>

        {/* Fatos */}
        <div>
          <FieldLabel>Fatos</FieldLabel>
          <Textarea
            value={proposta.fatos}
            onChange={(e) => onChange({ fatos: e.target.value })}
            rows={5}
            placeholder="Descrição dos fatos"
            aria-label="Fatos do caso"
          />
          <Origem
            valor={
              proposta.degradado
                ? null
                : proposta.fatos
                  ? "relato e documentos analisados"
                  : null
            }
          />
        </div>

        {/* Parte contrária */}
        <div>
          <FieldLabel>Parte contrária</FieldLabel>
          <Input
            value={proposta.parteContraria}
            onChange={(e) => onChange({ parteContraria: e.target.value })}
            placeholder="Nome da parte contrária"
            aria-label="Parte contrária"
          />
        </div>

        {/* Documentos — só quando o lote trouxe algum */}
        {proposta.documentos.length > 0 && (
          <div>
            <FieldLabel>Documentos</FieldLabel>
            <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 dark:divide-slate-700 dark:border-slate-600">
              {proposta.documentos.map((doc, i) => (
                <li
                  key={doc.documentId || `${doc.nome}-${i}`}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2 text-sm",
                    !doc.selecionado && "opacity-50",
                  )}
                >
                  <span className="min-w-0 flex-1 truncate text-slate-700 dark:text-slate-200">
                    {doc.nome}
                  </span>
                  <Badge tone={doc.classificacao ? "slate" : "amber"}>
                    {doc.classificacao ?? "não reconhecido"}
                  </Badge>
                  {doc.confianca != null && (
                    <ConfidenceBadge value={doc.confianca} />
                  )}
                  {doc.documentId && (
                    <button
                      type="button"
                      aria-label={
                        doc.selecionado
                          ? `Remover ${doc.nome} do caso`
                          : `Vincular ${doc.nome} ao caso`
                      }
                      title={
                        doc.selecionado
                          ? "Remover do caso (o arquivo não é apagado)"
                          : "Vincular ao caso"
                      }
                      onClick={() =>
                        onChange({
                          documentos: proposta.documentos.map((d, j) =>
                            j === i ? { ...d, selecionado: !d.selecionado } : d,
                          ),
                        })
                      }
                      className="shrink-0 rounded p-1 text-slate-400 hover:text-danger-500"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  )}
                </li>
              ))}
            </ul>
            <p className="mt-1 text-[11px] text-slate-400">
              os marcados serão vinculados ao caso; desmarcar não apaga o
              arquivo
            </p>
          </div>
        )}

        {/* Lacunas documentais/probatórias sugeridas na triagem. */}
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <FieldLabel>Documentos faltantes</FieldLabel>
            <Textarea
              value={listaParaTexto(proposta.documentosFaltantes)}
              onChange={(e) =>
                onChange({ documentosFaltantes: textoParaLista(e.target.value) })
              }
              rows={4}
              placeholder={"Um item por linha\nEx.: comprovante da negativação"}
              aria-label="Documentos faltantes"
            />
            <p className="mt-1 text-[11px] text-slate-400">
              Sugestões da triagem; remova o que não for necessário.
            </p>
          </div>
          <div>
            <FieldLabel>Provas / diligências necessárias</FieldLabel>
            <Textarea
              value={listaParaTexto(proposta.provasNecessarias)}
              onChange={(e) =>
                onChange({ provasNecessarias: textoParaLista(e.target.value) })
              }
              rows={4}
              placeholder={"Um item por linha\nEx.: confirmar data do evento"}
              aria-label="Provas necessárias"
            />
            <p className="mt-1 text-[11px] text-slate-400">
              Hipóteses para revisão; não são tratadas como fatos confirmados.
            </p>
          </div>
        </div>

        {/* Prazo detectado — só quando a análise achou um */}
        {proposta.prazo && (
          <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-3 dark:border-amber-800 dark:bg-amber-900/10">
            <FieldLabel>Prazo detectado</FieldLabel>
            <div className="flex flex-wrap items-center gap-2">
              <Input
                value={proposta.prazo.descricao}
                onChange={(e) => atualizarPrazo({ descricao: e.target.value })}
                placeholder="Descrição do prazo"
                aria-label="Descrição do prazo"
                className="min-w-48 flex-1"
              />
              <Input
                type="date"
                value={proposta.prazo.data.slice(0, 10)}
                onChange={(e) => atualizarPrazo({ data: e.target.value })}
                aria-label="Data do prazo"
                className="w-40"
              />
            </div>
            <Origem valor={proposta.prazo.origem} />
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
                <input
                  type="checkbox"
                  checked={proposta.prazo.criar}
                  onChange={(e) => atualizarPrazo({ criar: e.target.checked })}
                />
                criar este prazo
              </label>
              {proposta.prazo.criar && (
                <Select
                  value={proposta.prazo.responsavelId}
                  onChange={(e) =>
                    atualizarPrazo({ responsavelId: e.target.value })
                  }
                  aria-label="Responsável pelo prazo"
                  className="max-w-56"
                >
                  {responsaveis.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.full_name}
                    </option>
                  ))}
                  {!responsaveis.some(
                    (u) => u.id === proposta.prazo?.responsavelId,
                  ) &&
                    proposta.prazo.responsavelId && (
                      <option value={proposta.prazo.responsavelId}>eu</option>
                    )}
                </Select>
              )}
            </div>
          </div>
        )}

        {/* Próxima ação */}
        <div>
          <FieldLabel>Próxima ação</FieldLabel>
          <Input
            value={proposta.proximaAcao}
            onChange={(e) => onChange({ proximaAcao: e.target.value })}
            placeholder="Ex.: Notificação extrajudicial"
            aria-label="Próxima ação"
          />
        </div>

        <div>
          <FieldLabel>Próximos passos</FieldLabel>
          <Textarea
            value={listaParaTexto(proposta.proximosPassos)}
            onChange={(e) =>
              onChange({ proximosPassos: textoParaLista(e.target.value) })
            }
            rows={4}
            placeholder={"Um item por linha\nEx.: conferir documento X"}
            aria-label="Próximos passos"
          />
          <p className="mt-1 text-[11px] text-slate-400">
            Plano inicial de triagem. A “Próxima ação” acima continua sendo a
            providência operacional imediata do caso.
          </p>
        </div>

        {/* Responsável (por exceção: default é o próprio usuário) */}
        <div>
          <FieldLabel>Advogado responsável</FieldLabel>
          <Select
            value={proposta.advogadoResponsavelId}
            onChange={(e) =>
              onChange({ advogadoResponsavelId: e.target.value })
            }
            aria-label="Advogado responsável"
            className="max-w-72"
          >
            {!responsaveis.some(
              (u) => u.id === proposta.advogadoResponsavelId,
            ) &&
              proposta.advogadoResponsavelId && (
                <option value={proposta.advogadoResponsavelId}>eu</option>
              )}
            {responsaveis.map((u) => (
              <option key={u.id} value={u.id}>
                {u.full_name}
              </option>
            ))}
          </Select>
        </div>
      </Card>

      <label className="flex items-center gap-2 text-sm font-medium text-slate-800 dark:text-slate-100">
        <input
          type="checkbox"
          checked={proposta.confirmoRevisao}
          onChange={(e) => onChange({ confirmoRevisao: e.target.checked })}
        />
        Confirmo que revisei os dados acima
      </label>

      <div className="flex items-center justify-between">
        <Button variant="ghost" onClick={onDescartar} disabled={criando}>
          descartar
        </Button>
        <Button size="lg" disabled={!podeCriar} onClick={onCriar}>
          {criando
            ? "Processando…"
            : proposta.reconciliarCaseId
              ? "Vincular processo"
              : "Criar caso"}
        </Button>
      </div>
    </div>
  );
}
