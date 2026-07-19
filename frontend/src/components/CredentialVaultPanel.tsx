import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CircleOff,
  Download,
  History,
  KeyRound,
  Loader2,
  Pencil,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import api from "../lib/api";
import {
  cadastrarCredencial,
  historicoCampo,
  importarEnv,
  listarCofre,
  revogarCredencial,
  type CampoStatus,
  type CredencialMeta,
  type CredentialState,
  type ImportResumo,
  type ProviderStatus,
  type Reauth,
} from "../lib/cofre";
import { toast } from "./Toast";
import { Button, Input, Modal, SectionCard, Spinner } from "./UI";

// ── Catálogo de apresentação ─────────────────────────────
// provider_key → rótulo humano + grupo. O grupo espelha o painel de saúde
// (integration_status): Inteligência / Jurídico / Comunicação / Infraestrutura.
// O backend devolve os providers na ordem do credential_registry; aqui só
// atribuímos rótulo e grupo para exibição.
const GROUP_ORDER = [
  "Inteligência",
  "Jurídico",
  "Comunicação",
  "Infraestrutura",
  "Outras",
] as const;

const PROVIDER_META: Record<string, { label: string; group: string }> = {
  groq: { label: "Groq", group: "Inteligência" },
  anthropic: { label: "Anthropic (Claude)", group: "Inteligência" },
  maritaca: { label: "Maritaca (Sabiá)", group: "Inteligência" },
  datajud: { label: "DataJud / CNJ", group: "Jurídico" },
  transparencia: { label: "Portal da Transparência", group: "Jurídico" },
  infosimples: { label: "Infosimples", group: "Jurídico" },
  whatsapp_zapi: { label: "WhatsApp (Z-API)", group: "Comunicação" },
  smtp: { label: "E-mail (SMTP)", group: "Comunicação" },
  push_vapid: { label: "Web Push (VAPID)", group: "Comunicação" },
  nfse: { label: "NFS-e (NuvemFiscal)", group: "Infraestrutura" },
  langfuse: { label: "Langfuse", group: "Infraestrutura" },
};

function providerLabel(providerKey: string): string {
  return PROVIDER_META[providerKey]?.label ?? providerKey;
}

function providerGroup(providerKey: string): string {
  return PROVIDER_META[providerKey]?.group ?? "Outras";
}

/** Agrupa providers pelos grupos institucionais, preservando a ordem do backend. */
export function groupProviders(
  providers: ProviderStatus[],
): Array<[string, ProviderStatus[]]> {
  const buckets = new Map<string, ProviderStatus[]>();
  for (const provider of providers) {
    const group = providerGroup(provider.provider_key);
    buckets.set(group, [...(buckets.get(group) ?? []), provider]);
  }
  return GROUP_ORDER.filter((group) => buckets.has(group)).map((group) => [
    group,
    buckets.get(group) as ProviderStatus[],
  ]);
}

// ── Estado/badge de um campo ─────────────────────────────
const STATE_META: Record<
  CredentialState,
  { label: string; className: string }
> = {
  configurada: { label: "Configurada", className: "badge-success" },
  ausente: { label: "Ausente", className: "badge-neutral" },
  invalida: { label: "Inválida", className: "badge-danger" },
  expirada: { label: "Expirada", className: "badge-warn" },
  sem_permissao: { label: "Sem permissão", className: "badge-danger" },
  indisponivel: { label: "Indisponível", className: "badge-neutral" },
};

// last_test_status → estado exibível (reservado aos testadores, PR-4). Só os
// valores conhecidos "sobem" o card para um estado de atenção/erro.
const TEST_STATE: Record<string, CredentialState> = {
  invalida: "invalida",
  expirada: "expirada",
  sem_permissao: "sem_permissao",
  indisponivel: "indisponivel",
};

/** Estado efetivo de um campo: ausente > resultado de teste > configurada. */
export function resolveCredentialState(campo: CampoStatus): CredentialState {
  if (campo.estado === "ausente") {
    return "ausente";
  }
  const test = campo.last_test_status
    ? TEST_STATE[campo.last_test_status]
    : undefined;
  return test ?? "configurada";
}

function fmtDateTime(value?: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

const ORIGEM_LABEL: Record<string, string> = {
  manual: "cadastro manual",
  env_import: "importada do .env",
};

// ── Campos comuns de step-up (reautenticação) ────────────
// Reusado por todos os modais mutadores. O valor do segredo NUNCA passa por
// aqui — só a senha atual e o TOTP.
function StepUpFields({
  senha,
  setSenha,
  totp,
  setTotp,
  totpEnabled,
}: {
  senha: string;
  setSenha: (v: string) => void;
  totp: string;
  setTotp: (v: string) => void;
  totpEnabled: boolean;
}) {
  return (
    <>
      <label className="block">
        <span className="text-xs font-medium text-slate-500">
          Sua senha atual
        </span>
        <Input
          type="password"
          autoComplete="current-password"
          value={senha}
          onChange={(e) => setSenha(e.target.value)}
          placeholder="Confirme sua identidade"
          required
        />
      </label>
      {totpEnabled && (
        <label className="block">
          <span className="text-xs font-medium text-slate-500">
            Código do autenticador (2FA)
          </span>
          <Input
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={totp}
            onChange={(e) =>
              setTotp(e.target.value.replace(/\D/g, "").slice(0, 6))
            }
            placeholder="000000"
          />
        </label>
      )}
    </>
  );
}

function reauthFrom(senha: string, totp: string, totpEnabled: boolean): Reauth {
  return { senha_atual: senha, codigo_totp: totpEnabled ? totp : undefined };
}

function apiError(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail;
  return typeof detail === "string" ? detail : fallback;
}

// ── Modal: cadastrar / substituir ────────────────────────
// O segredo digitado vive SÓ no estado local deste modal e é apagado ao fechar
// (o modal é desmontado quando fecha) — nunca sobe para estado global nem log.
function CadastroModal({
  provider,
  campo,
  jaConfigurada,
  totpEnabled,
  onClose,
  onDone,
}: {
  provider: string;
  campo: CampoStatus;
  jaConfigurada: boolean;
  totpEnabled: boolean;
  onClose: () => void;
  onDone: () => void;
}) {
  const [valor, setValor] = useState("");
  const [senha, setSenha] = useState("");
  const [totp, setTotp] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (!valor.trim() || !senha) {
      toast.error("Informe o segredo e sua senha atual.");
      return;
    }
    setSaving(true);
    try {
      const meta = await cadastrarCredencial(
        provider,
        campo.field_key,
        valor,
        reauthFrom(senha, totp, totpEnabled),
      );
      // Limpa o segredo do estado local ANTES de qualquer render/close.
      setValor("");
      setSenha("");
      setTotp("");
      if (meta.overlay_aplicado === false) {
        toast.error(
          "Credencial gravada, mas ainda não propagada ao ambiente. Recarregue em instantes.",
        );
      } else {
        toast.success(
          jaConfigurada ? "Credencial substituída." : "Credencial cadastrada.",
        );
      }
      onDone();
      onClose();
    } catch (error) {
      toast.error(apiError(error, "Não foi possível salvar a credencial."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title={`${jaConfigurada ? "Substituir" : "Cadastrar"} — ${providerLabel(provider)}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            Cancelar
          </Button>
          <Button
            onClick={submit}
            disabled={saving}
            icon={
              saving ? <Loader2 className="h-4 w-4 animate-spin" /> : undefined
            }
          >
            {jaConfigurada ? "Substituir" : "Cadastrar"}
          </Button>
        </>
      }
    >
      <form
        autoComplete="off"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
        className="space-y-4"
      >
        <p className="text-xs text-slate-500">{campo.rotulo}</p>
        <label className="block">
          <span className="text-xs font-medium text-slate-500">
            Novo segredo
          </span>
          <Input
            type="password"
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
            spellCheck={false}
            value={valor}
            onChange={(e) => setValor(e.target.value)}
            placeholder="Cole aqui o valor do segredo"
            required
          />
          <span className="mt-1 block text-[11px] text-slate-400">
            O valor é enviado cifrado e nunca é exibido de volta — só os 4
            últimos dígitos ficam visíveis.
          </span>
        </label>
        <StepUpFields
          senha={senha}
          setSenha={setSenha}
          totp={totp}
          setTotp={setTotp}
          totpEnabled={totpEnabled}
        />
      </form>
    </Modal>
  );
}

// ── Modal: revogar (confirmação dupla + senha) ───────────
function RevogarModal({
  provider,
  campo,
  totpEnabled,
  onClose,
  onDone,
}: {
  provider: string;
  campo: CampoStatus;
  totpEnabled: boolean;
  onClose: () => void;
  onDone: () => void;
}) {
  const [confirmado, setConfirmado] = useState(false);
  const [senha, setSenha] = useState("");
  const [totp, setTotp] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (!confirmado || !senha) return;
    setSaving(true);
    try {
      const meta = await revogarCredencial(
        provider,
        campo.field_key,
        reauthFrom(senha, totp, totpEnabled),
      );
      setSenha("");
      setTotp("");
      if (meta.overlay_aplicado === false) {
        toast.error(
          "Credencial revogada, mas ainda não propagada ao ambiente. Recarregue em instantes.",
        );
      } else {
        toast.success("Credencial revogada.");
      }
      onDone();
      onClose();
    } catch (error) {
      toast.error(apiError(error, "Não foi possível revogar a credencial."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title={`Revogar — ${providerLabel(provider)}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            Cancelar
          </Button>
          <Button
            variant="danger"
            onClick={submit}
            disabled={saving || !confirmado || !senha}
            icon={
              saving ? <Loader2 className="h-4 w-4 animate-spin" /> : undefined
            }
          >
            Revogar definitivamente
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="flex items-start gap-2 rounded-xl border border-danger-200 bg-danger-50/60 p-3 text-sm text-danger-700">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            A integração <strong>{providerLabel(provider)}</strong> deixará de
            funcionar imediatamente. A revogação zera o valor sem retornar ao
            <code className="mx-1">.env</code> — só um novo cadastro reativa.
          </div>
        </div>
        <label className="flex items-start gap-2 text-sm text-slate-600">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={confirmado}
            onChange={(e) => setConfirmado(e.target.checked)}
          />
          <span>
            Entendo o impacto e confirmo a revogação de{" "}
            <strong>{campo.rotulo}</strong>.
          </span>
        </label>
        <StepUpFields
          senha={senha}
          setSenha={setSenha}
          totp={totp}
          setTotp={setTotp}
          totpEnabled={totpEnabled}
        />
      </div>
    </Modal>
  );
}

// ── Modal: histórico de versões (só metadados) ───────────
function HistoricoModal({
  provider,
  campo,
  onClose,
}: {
  provider: string;
  campo: CampoStatus;
  onClose: () => void;
}) {
  const [linhas, setLinhas] = useState<CredencialMeta[] | null>(null);

  useEffect(() => {
    let vivo = true;
    historicoCampo(provider, campo.field_key)
      .then((data) => vivo && setLinhas(data))
      .catch(
        (error) =>
          vivo &&
          (setLinhas([]),
          toast.error(
            apiError(error, "Não foi possível carregar o histórico."),
          )),
      );
    return () => {
      vivo = false;
    };
  }, [provider, campo.field_key]);

  return (
    <Modal open onClose={onClose} title={`Histórico — ${campo.rotulo}`}>
      {linhas === null ? (
        <Spinner />
      ) : linhas.length === 0 ? (
        <p className="text-sm text-slate-500">
          Nenhuma versão registrada para este campo.
        </p>
      ) : (
        <ul className="space-y-2">
          {linhas.map((linha) => (
            <li
              key={linha.id}
              className="card flex flex-wrap items-center justify-between gap-2 p-3 text-sm"
            >
              <span className="font-medium text-slate-800">
                v{linha.versao}{" "}
                <span className="font-mono text-slate-400">
                  ••••{linha.last4 || "----"}
                </span>
              </span>
              <span className="flex items-center gap-2 text-xs text-slate-500">
                <span
                  className={`badge ${linha.ativo ? "badge-success" : "badge-neutral"}`}
                >
                  {linha.ativo
                    ? "vigente"
                    : linha.revoked_at
                      ? "revogada"
                      : "substituída"}
                </span>
                <span>{ORIGEM_LABEL[linha.origem] ?? linha.origem}</span>
                <span>{fmtDateTime(linha.updated_at ?? linha.created_at)}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}

// ── Modal: importar do .env ──────────────────────────────
function ImportarEnvModal({
  totpEnabled,
  onClose,
  onDone,
}: {
  totpEnabled: boolean;
  onClose: () => void;
  onDone: () => void;
}) {
  const [senha, setSenha] = useState("");
  const [totp, setTotp] = useState("");
  const [saving, setSaving] = useState(false);
  const [resumo, setResumo] = useState<ImportResumo | null>(null);

  const submit = async () => {
    if (!senha) return;
    setSaving(true);
    try {
      const data = await importarEnv(reauthFrom(senha, totp, totpEnabled));
      setSenha("");
      setTotp("");
      setResumo(data);
      onDone();
    } catch (error) {
      toast.error(apiError(error, "Não foi possível importar do .env."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title="Importar credenciais do .env"
      footer={
        resumo ? (
          <Button onClick={onClose}>Concluir</Button>
        ) : (
          <>
            <Button variant="ghost" onClick={onClose} disabled={saving}>
              Cancelar
            </Button>
            <Button
              onClick={submit}
              disabled={saving || !senha}
              icon={
                saving ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : undefined
              }
            >
              Importar
            </Button>
          </>
        )
      }
    >
      {resumo ? (
        <div className="space-y-3">
          <p className="text-sm text-slate-600">
            {resumo.total === 0
              ? "Nenhuma credencial nova foi importada (as do catálogo já estão no cofre)."
              : `${resumo.total} credencial(is) importada(s) do ambiente para o cofre.`}
          </p>
          {resumo.importados.length > 0 && (
            <ul className="space-y-1">
              {resumo.importados.map((item) => (
                <li
                  key={`${item.provider}/${item.field}`}
                  className="flex items-center justify-between rounded-lg bg-slate-900/[0.04] px-3 py-2 text-xs dark:bg-white/[0.06]"
                >
                  <span className="font-medium text-slate-700">
                    {providerLabel(item.provider)} · {item.field}
                  </span>
                  <span className="font-mono text-slate-400">
                    ••••{item.last4 || "----"}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {resumo.overlay_aplicado === false && (
            <p className="text-xs text-danger-600">
              Importado, mas ainda não propagado ao ambiente. Recarregue em
              instantes.
            </p>
          )}
        </div>
      ) : (
        <form
          autoComplete="off"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
          className="space-y-4"
        >
          <p className="text-xs text-slate-500">
            Copia para o cofre os segredos do catálogo que ainda existem apenas
            no <code>.env</code>. Idempotente e sem exibir valores.
          </p>
          <StepUpFields
            senha={senha}
            setSenha={setSenha}
            totp={totp}
            setTotp={setTotp}
            totpEnabled={totpEnabled}
          />
        </form>
      )}
    </Modal>
  );
}

// ── Card de um campo ─────────────────────────────────────
function CampoRow({
  provider,
  campo,
  onCadastrar,
  onRevogar,
  onHistorico,
}: {
  provider: string;
  campo: CampoStatus;
  onCadastrar: () => void;
  onRevogar: () => void;
  onHistorico: () => void;
}) {
  const state = resolveCredentialState(campo);
  const meta = STATE_META[state];
  const configurada = campo.estado === "configurada";

  return (
    <div className="card flex flex-col gap-3 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-slate-800">
              {campo.rotulo}
            </span>
            <span className={`badge ${meta.className}`}>{meta.label}</span>
            {!campo.obrigatorio && (
              <span className="badge badge-neutral">opcional</span>
            )}
          </div>
          <div className="mt-1 font-mono text-xs text-slate-500">
            {configurada ? `••••${campo.last4 || "----"}` : "não configurada"}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <Button
            size="sm"
            variant={configurada ? "secondary" : "primary"}
            onClick={onCadastrar}
            icon={
              configurada ? (
                <Pencil className="h-3.5 w-3.5" />
              ) : (
                <KeyRound className="h-3.5 w-3.5" />
              )
            }
          >
            {configurada ? "Substituir" : "Cadastrar"}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={onHistorico}
            aria-label="Histórico"
            icon={<History className="h-3.5 w-3.5" />}
          />
          {configurada && (
            <Button
              size="sm"
              variant="ghost"
              onClick={onRevogar}
              aria-label="Revogar"
              icon={<Trash2 className="h-3.5 w-3.5 text-danger-600" />}
            />
          )}
        </div>
      </div>
      {configurada && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-400">
          {campo.versao != null && <span>versão {campo.versao}</span>}
          <span>
            alterada em {fmtDateTime(campo.updated_at ?? campo.created_at)}
          </span>
          {campo.origem && (
            <span>· {ORIGEM_LABEL[campo.origem] ?? campo.origem}</span>
          )}
          {campo.last_test_status && (
            <span>
              · último teste: {campo.last_test_detail || campo.last_test_status}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

// ── Painel ───────────────────────────────────────────────
type ModalKind = "cadastrar" | "revogar" | "historico";

interface ModalTarget {
  kind: ModalKind;
  provider: string;
  campo: CampoStatus;
}

export default function CredentialVaultPanel() {
  const [providers, setProviders] = useState<ProviderStatus[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [totpEnabled, setTotpEnabled] = useState(false);
  const [target, setTarget] = useState<ModalTarget | null>(null);
  const [importando, setImportando] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [cofre, security] = await Promise.all([
        listarCofre(),
        api
          .get<{ totp_enabled: boolean }>("/users/me/security")
          .then((r) => r.data)
          .catch(() => null),
      ]);
      setProviders(cofre);
      if (security) setTotpEnabled(Boolean(security.totp_enabled));
    } catch (error) {
      toast.error(apiError(error, "Não foi possível carregar o cofre."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const grupos = useMemo(() => groupProviders(providers ?? []), [providers]);

  const totalConfiguradas = useMemo(
    () =>
      (providers ?? []).reduce(
        (acc, p) =>
          acc + p.campos.filter((c) => c.estado === "configurada").length,
        0,
      ),
    [providers],
  );
  const totalCampos = useMemo(
    () => (providers ?? []).reduce((acc, p) => acc + p.campos.length, 0),
    [providers],
  );

  return (
    <div className="space-y-5">
      <SectionCard
        title="Cofre de credenciais"
        subtitle="Segredos que o EJC USA para falar com serviços externos (DataJud, Groq, SMTP, Z-API…). Não confundir com API Keys, que são as chaves que o EJC EMITE para integradores externos consumirem esta API."
        actions={
          <>
            <Button
              variant="secondary"
              onClick={() => setImportando(true)}
              icon={<Download className="h-4 w-4" />}
            >
              Importar do .env
            </Button>
            <Button
              variant="ghost"
              onClick={load}
              disabled={loading}
              icon={
                <RefreshCw
                  className={`h-4 w-4 ${loading ? "animate-spin" : ""}`}
                />
              }
              aria-label="Atualizar"
            />
          </>
        }
      >
        <div className="flex items-start gap-2 rounded-xl border border-primary-200 bg-primary-50/50 p-4 text-sm text-slate-600">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary-600" />
          <div>
            Nenhum valor de segredo é retornado ao navegador — só os 4 últimos
            dígitos e metadados. Cadastrar, substituir, revogar e importar
            exigem sua senha atual{totpEnabled ? " e o código do 2FA" : ""}.
            <div className="mt-1 text-xs text-slate-400">
              {totalConfiguradas} de {totalCampos} campos configurados.
            </div>
          </div>
        </div>
      </SectionCard>

      {loading && !providers ? (
        <Spinner />
      ) : (
        grupos.map(([grupo, lista]) => (
          <SectionCard key={grupo} title={grupo}>
            <div className="space-y-4">
              {lista.map((provider) => (
                <div key={provider.provider_key}>
                  <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
                    {providerLabel(provider.provider_key)}
                  </div>
                  {provider.campos.length === 0 ? (
                    <p className="text-xs text-slate-400">
                      Nenhum campo no catálogo.
                    </p>
                  ) : (
                    <div className="grid gap-3 md:grid-cols-2">
                      {provider.campos.map((campo) => (
                        <CampoRow
                          key={campo.field_key}
                          provider={provider.provider_key}
                          campo={campo}
                          onCadastrar={() =>
                            setTarget({
                              kind: "cadastrar",
                              provider: provider.provider_key,
                              campo,
                            })
                          }
                          onRevogar={() =>
                            setTarget({
                              kind: "revogar",
                              provider: provider.provider_key,
                              campo,
                            })
                          }
                          onHistorico={() =>
                            setTarget({
                              kind: "historico",
                              provider: provider.provider_key,
                              campo,
                            })
                          }
                        />
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </SectionCard>
        ))
      )}

      {providers && grupos.length === 0 && !loading && (
        <SectionCard title="Cofre">
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <CircleOff className="h-4 w-4" /> Nenhum provider no catálogo de
            credenciais.
          </div>
        </SectionCard>
      )}

      {target?.kind === "cadastrar" && (
        <CadastroModal
          provider={target.provider}
          campo={target.campo}
          jaConfigurada={target.campo.estado === "configurada"}
          totpEnabled={totpEnabled}
          onClose={() => setTarget(null)}
          onDone={load}
        />
      )}
      {target?.kind === "revogar" && (
        <RevogarModal
          provider={target.provider}
          campo={target.campo}
          totpEnabled={totpEnabled}
          onClose={() => setTarget(null)}
          onDone={load}
        />
      )}
      {target?.kind === "historico" && (
        <HistoricoModal
          provider={target.provider}
          campo={target.campo}
          onClose={() => setTarget(null)}
        />
      )}
      {importando && (
        <ImportarEnvModal
          totpEnabled={totpEnabled}
          onClose={() => setImportando(false)}
          onDone={load}
        />
      )}
    </div>
  );
}
