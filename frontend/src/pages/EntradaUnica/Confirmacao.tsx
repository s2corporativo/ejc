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
        .get("/clients", { params: { search: limpo, page_size: 8 } })
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
  const precisaConfirmarDuplicado =
    proposta.duplicados.length > 0 && !proposta.clienteId;

  const podeCriar =
    proposta.confirmoRevisao &&
    (!precisaConfirmarConflito || proposta.conflictConfirmed) &&
    (!precisaConfirmarDuplicado || proposta.duplicateConfirmed) &&
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
        <span className="text-xs text-slate-400">rascunho</span>
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
                  onChange({ clienteId: null });
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
                Cliente possivelmente já cadastrado
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
                  Não é o mesmo cliente — cadastrar como novo
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
          {criando ? "Criando…" : "Criar caso"}
        </Button>
      </div>
    </div>
  );
}
